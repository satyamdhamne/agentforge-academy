BLUEPRINT = {
    "category": "Data Engineering",
    "level": "intermediate",
    "build_hours": 6,
    "tags": ["sql", "text-to-sql", "analytics", "guardrails"],
    "summary": "Turns analytics questions into a single read-only SQL query, executes it under an authorizer and time limit, and self-corrects on errors.",
    "problem": "Non-specialists wait on analysts for simple questions; ad-hoc SQL written by models can be wrong, slow or destructive.",
    "business_value": "Self-serve answers for common questions with guardrails that make it safe to run generated SQL against real data.",
    "inputs": ["Natural-language question", "Max rows to return"],
    "outputs": ["SQL, explanation and stated assumptions", "Columns and rows (capped)", "Attempt history including database errors",
                "Clarification question when the request is ambiguous"],
    "prerequisites": ["SQL joins and aggregation", "Database permissions", "Structured outputs"],
    "verdict": "workflow",
    "verdict_reasoning": "Generate → validate → execute → (on error) correct is a bounded loop with a fixed toolset. The model "
                         "never chooses arbitrary actions, and the loop is capped at 3 attempts. For a fixed set of popular "
                         "questions, curated saved queries or a semantic layer (dbt metrics, Cube) beat text-to-SQL entirely.",
    "architecture_mermaid": """flowchart LR
    Q[Question] --> G[LLM: draft SQL]
    S[(Schema + conventions)] --> G
    G --> C{static check}
    C -->|ok| E[execute: query_only + authorizer + timeout]
    C -->|reject| F[feed error back]
    E -->|db error| F
    F --> G
    E -->|rows| R[Answer]
    G -->|ambiguous| K[Clarifying question]""",
    "data_flow": [
        "Schema DDL, sample categorical values and business conventions (what counts as revenue) go into the system prompt.",
        "The model returns JSON: sql, explanation, assumptions or a clarification request.",
        "Static check: must start with SELECT/WITH, single statement.",
        "Execution with PRAGMA query_only, an authorizer that only allows read operations, a progress-handler timeout and a row cap.",
        "Database errors are fed back for up to 3 total attempts.",
    ],
    "framework": {"choice": "Plain Python", "reasoning": "A bounded retry loop is a for-loop. LangChain's SQL toolkits add convenience but hide the guardrails learners need to see."},
    "model_selection": {"recommended": "Strong code model with JSON output.", "reasoning": "SQL correctness matters more than latency; errors cost an extra round trip.",
                        "alternatives": ["Fine-tuned small model on your own query log", "Semantic layer instead of free-form SQL"]},
    "state_memory": "Per run: conversation with prior failed SQL and errors. No cross-run memory; production systems add a vetted query library for retrieval (few-shot examples).",
    "security": [
        {"threat": "Destructive SQL (DROP/UPDATE/DELETE)", "mitigation": "Read-only DB user in production; here query_only + authorizer denies all non-read actions regardless of what the model writes."},
        {"threat": "Expensive queries (cartesian joins)", "mitigation": "Execution time limit, row cap, and statement_timeout on real databases."},
        {"threat": "Data exposure across tenants/roles", "mitigation": "Run as a role with row-level security; never rely on the prompt for access control."},
        {"threat": "Prompt injection via data values", "mitigation": "Only schema and samples go to the model; query results are returned to the user, not the model."},
    ],
    "cost_latency": "Schema prompt ≈1-2k tokens, output ≈200 tokens per attempt; worst case 3 attempts. Cache schema descriptions and use prompt caching where supported.",
    "failure_modes": [
        {"mode": "Semantically wrong but valid SQL", "mitigation": "Show SQL + assumptions to the user; evaluate on a gold question set; maintain a semantic layer."},
        {"mode": "Hallucinated columns", "mitigation": "Database error feeds back into correction; the schema prompt is authoritative."},
        {"mode": "Ambiguous metric names", "mitigation": "Conventions in the prompt and clarification path."},
    ],
    "improvements": ["Retrieve similar vetted queries as few-shot examples", "Result-set sanity checks (empty, huge)", "Chart suggestions", "Query cost estimation via EXPLAIN before execution"],
    "production_checklist": ["Read-only database role", "Statement timeout", "Row-level security", "Audit log of generated SQL", "Gold-set regression tests"],
    "challenges": [
        {"level": "beginner", "title": "New intent", "description": "Add support for 'revenue by country' to the mock and an eval case."},
        {"level": "intermediate", "title": "EXPLAIN gate", "description": "Reject queries whose EXPLAIN QUERY PLAN shows a full scan on order_items without a filter."},
        {"level": "advanced", "title": "Few-shot retrieval", "description": "Store vetted question→SQL pairs and retrieve the top 3 as examples; measure accuracy change on the eval set."},
    ],
    "interview_questions": [
        {"q": "Why isn't a 'only generate SELECT' prompt enough for safety?", "a": "Prompts are not enforcement. Use a read-only role, database-level permissions and an authorizer/allowlist."},
        {"q": "How do you evaluate text-to-SQL?", "a": "Execution accuracy: compare result sets of generated vs gold SQL on a fixed database, not string equality."},
        {"q": "When would you not build text-to-SQL?", "a": "When a small set of well-known metrics covers most questions - a semantic layer or dashboards are cheaper and more reliable."},
    ],
}
