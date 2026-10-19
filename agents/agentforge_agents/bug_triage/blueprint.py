BLUEPRINT = {
    "category": "Developer Productivity",
    "level": "advanced",
    "build_hours": 10,
    "tags": ["agent-loop", "tool-calling", "human-in-the-loop", "issue-tracking"],
    "summary": "A true tool-calling agent: it chooses which tools to call to gather evidence, then proposes a triage decision that only a human can apply.",
    "problem": "New bug reports pile up untriaged; duplicates, regressions and ownership are discovered late.",
    "business_value": "Faster routing to the right team, earlier regression detection, fewer duplicate investigations - with a human in control of every change.",
    "inputs": ["Issue title, body (may contain a stack trace) and reporter"],
    "outputs": ["Decision: severity, component, labels, team, duplicate_of, reasoning", "Step-by-step tool trace",
                "Guardrail notes", "Pending action `apply_triage` awaiting approval"],
    "prerequisites": ["Tool/function calling", "Agent loops and stopping conditions", "Human-in-the-loop design"],
    "verdict": "agent",
    "verdict_reasoning": "The evidence needed varies per report: some have stack traces, some need deploy history, some are obvious "
                         "duplicates. Letting the model choose tools avoids wasted calls and handles the long tail. The loop is "
                         "still bounded (8 steps, token/time budget), read-only, and every write goes through approval. If 90% of "
                         "your bugs look alike, a fixed workflow (always parse → search → owners) is simpler and nearly as good.",
    "architecture_mermaid": """flowchart TD
    I[Issue] --> L{LLM chooses next step}
    L -->|tool call| T[Allowlisted read-only tools]
    T -->|validated args, result as untrusted data| L
    L -->|finalize_triage| G[guardrails: labels allowlist, duplicate must be a search hit]
    G --> P[[Pending action: apply_triage]]
    P -->|human approves| A[Tracker updated + audit log]
    P -->|human rejects| R[No change]
    L -->|budget/steps exhausted| X[Incomplete → human]""",
    "data_flow": [
        "The model sees the issue (fenced) and specs for five tools; apply_triage is not offered to the model at all.",
        "Each tool call's arguments are validated with Pydantic before execution; errors are returned to the model so it can recover.",
        "Search results are recorded so duplicate_of can be checked against ids the agent actually saw.",
        "finalize_triage ends the loop; guardrails clean the decision; the write is returned as a pending action.",
        "The platform executes apply_triage only after an authorised user approves, and writes an audit log entry.",
    ],
    "framework": {"choice": "Plain Python loop (maps 1:1 to LangGraph)", "reasoning": "The loop is ~40 lines so learners can see every "
                  "decision. In LangGraph: an `agent` node, a `tools` node, a conditional edge on tool_calls, and an `interrupt` "
                  "before the apply node for approval with a checkpointer for durable resume."},
    "model_selection": {"recommended": "Model with strong tool-calling reliability.", "reasoning": "Tool choice and argument quality drive outcomes; cheaper models often loop or call tools with bad arguments.",
                        "alternatives": ["Smaller model + fixed workflow", "Mock scripted policy for CI"]},
    "state_memory": "Short-term: the message list (tool calls and results) within one run. No long-term memory. For durable execution across approval delays, persist the state (run record + pending action) - which the platform does.",
    "security": [
        {"threat": "Agent performing unintended writes", "mitigation": "Write tool is not exposed to the model; side-effect tools require explicit approval in the registry; approval checked server-side."},
        {"threat": "Indirect prompt injection via issue text or tool results", "mitigation": "Untrusted data fenced; tools are read-only; decision validated against allowlists."},
        {"threat": "Runaway loops and cost", "mitigation": "Max 8 steps, token and wall-clock budget, single nudge if the model stops calling tools."},
        {"threat": "Over-privileged tracker credentials", "mitigation": "Production token scoped to labels/comments on one project; stored in a secrets manager, never in the prompt."},
    ],
    "cost_latency": "Each step re-sends the conversation: cost grows roughly quadratically with steps. Typical run: 4-5 steps × 1.5-3k tokens. Cap steps and truncate tool results (6k chars here).",
    "failure_modes": [
        {"mode": "Model never calls finalize", "mitigation": "One nudge, then stop with an incomplete result for a human."},
        {"mode": "Hallucinated duplicate ids", "mitigation": "Must match an id returned by search, otherwise cleared."},
        {"mode": "Tool argument errors", "mitigation": "Validation errors returned as tool results so the model can correct itself."},
    ],
    "improvements": ["Port to LangGraph with a checkpointer and interrupt", "Fetch the code at the failing frame", "Reporter follow-up questions for needs-info", "Learn from approve/reject decisions"],
    "production_checklist": ["Scoped tracker token in secrets manager", "Approval UI with diff of changes", "Audit log", "Step/token budgets", "Eval set of historical issues"],
    "challenges": [
        {"level": "beginner", "title": "New tool", "description": "Add a read-only get_issue_comments tool and use it in the mock policy."},
        {"level": "intermediate", "title": "Reject with feedback", "description": "When a human rejects, resume the loop with their feedback as a new user message."},
        {"level": "advanced", "title": "LangGraph port", "description": "Re-implement with LangGraph using interrupt_before the apply node and a Postgres checkpointer; prove resume after a restart."},
    ],
    "interview_questions": [
        {"q": "How do you make an agent safe to connect to a system that can write?", "a": "Least privilege tools, keep write tools out of the model's toolset or behind approval, validate arguments, audit every action."},
        {"q": "What stops an agent loop from running forever?", "a": "Step limits, token/time budgets, terminal tools, and handling of 'no tool call' replies."},
        {"q": "Agent or workflow for triage?", "a": "Agent when evidence needs vary per input; workflow when every input needs the same steps. Measure both."},
    ],
}
