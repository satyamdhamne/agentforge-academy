"""SQL Query Assistant: natural language -> validated, read-only SQL with a bounded self-correction loop."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core import AgentContext, CompletionRequest, Message
from .tools import SQLGuardError, build_demo_db, describe_schema, execute_readonly

SYSTEM_PROMPT = """You translate analytics questions into a single read-only SQLite query.

Schema and conventions:
{schema}

Rules:
- Output one SELECT (or WITH ... SELECT) statement. Never modify data.
- Use only tables and columns from the schema. Prefer explicit JOINs and column aliases.
- Add ORDER BY for ranked results and LIMIT when the question implies "top N".
- If the question is ambiguous or cannot be answered from the schema, set needs_clarification=true
  and ask one short question instead of guessing.
- List any assumptions you made (e.g. which order statuses count as revenue)."""

MAX_ATTEMPTS = 3


class SQLAssistantInput(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    max_rows: int = Field(50, ge=1, le=200)


class SQLDraft(BaseModel):
    sql: str = ""
    explanation: str = ""
    assumptions: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


def run(inp: SQLAssistantInput, ctx: AgentContext) -> dict:
    conn = ctx.step("build_demo_db", build_demo_db)
    schema = ctx.step("describe_schema", describe_schema, conn)
    messages = [Message("system", SYSTEM_PROMPT.format(schema=schema)), Message("user", inp.question)]
    attempts: list[dict] = []
    draft = SQLDraft()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft = ctx.structured(
            CompletionRequest(task="sql_assistant.generate", messages=messages, max_tokens=800,
                              context={"question": inp.question, "attempt": attempt,
                                       "last_error": attempts[-1]["error"] if attempts else None}),
            SQLDraft,
        )
        if draft.needs_clarification:
            return {"needs_clarification": True, "clarification_question": draft.clarification_question,
                    "sql": None, "columns": [], "rows": [], "row_count": 0, "truncated": False,
                    "explanation": draft.explanation, "assumptions": draft.assumptions, "attempts": attempts}
        try:
            result = ctx.step("execute_readonly", execute_readonly, conn, draft.sql, inp.max_rows)
            attempts.append({"attempt": attempt, "sql": draft.sql, "error": None})
            return {"needs_clarification": False, "clarification_question": "", "sql": draft.sql,
                    "explanation": draft.explanation, "assumptions": draft.assumptions, "attempts": attempts, **result}
        except SQLGuardError as exc:
            attempts.append({"attempt": attempt, "sql": draft.sql, "error": str(exc)})
            # Self-correction: show the model its own SQL and the database error, then retry.
            messages = messages + [
                Message("assistant", draft.sql),
                Message("user", f"That query failed with: {exc}. Return a corrected query."),
            ]
    return {"needs_clarification": False, "clarification_question": "", "sql": draft.sql, "columns": [], "rows": [],
            "row_count": 0, "truncated": False, "explanation": "Could not produce a valid query.",
            "assumptions": draft.assumptions, "attempts": attempts, "error": attempts[-1]["error"]}
