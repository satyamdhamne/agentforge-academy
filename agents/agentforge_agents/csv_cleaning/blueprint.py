BLUEPRINT = {
    "category": "Data Engineering",
    "level": "beginner",
    "build_hours": 4,
    "tags": ["data-quality", "csv", "etl", "planner-executor"],
    "summary": "Profiles a CSV, has a model propose a plan from an allowlist of cleaning operations, and applies the plan deterministically with a change log.",
    "problem": "Spreadsheets exported from different systems arrive with mixed date formats, currency strings, inconsistent categories and duplicates.",
    "business_value": "Fast, reviewable cleaning with an audit trail of exactly what changed - without giving a model the ability to rewrite data freely.",
    "inputs": ["CSV text (comma, semicolon, tab or pipe delimited)", "Optional goals for the data"],
    "outputs": ["Column profile (types, nulls, issues)", "Validated plan and rejected steps", "Per-operation change log", "Cleaned CSV and preview"],
    "prerequisites": ["CSV basics", "Data types and ISO 8601 dates", "Planner/executor pattern"],
    "verdict": "workflow",
    "verdict_reasoning": "The model is a planner choosing from ten safe operations; execution is pure code. For a recurring feed with a known schema, a fixed script or dbt tests are better - the model adds value only for unfamiliar files.",
    "architecture_mermaid": """flowchart LR
    C[CSV] --> R[read + sniff dialect]
    R --> P[profile columns]
    P --> L[LLM: plan from allowlist]
    L --> V{validate plan}
    V -->|rejected| X[rejected steps]
    V --> A[apply ops deterministically]
    A --> O[cleaned CSV + change log + after-profile]""",
    "data_flow": [
        "Dialect is sniffed; rows are padded/truncated to the header width.",
        "Each column gets an inferred type and issue list; date columns get a day-first inference.",
        "The model returns an ordered plan; unknown ops, unknown columns and invalid params are rejected.",
        "Operations are applied in order with counts of changed and unparsed cells; the result is re-profiled.",
    ],
    "framework": {"choice": "Plain Python (stdlib csv)", "reasoning": "No pandas dependency needed at this scale; swap to pandas/Polars for large files."},
    "model_selection": {"recommended": "Small model with JSON output.", "reasoning": "The model sees a compact profile, not the data, and chooses among few options.",
                        "alternatives": ["Rules only (the mock planner is a realistic baseline)"]},
    "state_memory": "Stateless. Save accepted plans per source so the next file from the same feed reuses a reviewed plan.",
    "security": [
        {"threat": "Model-generated transformations corrupting data", "mitigation": "Allowlisted ops only, validated parameters, original data untouched, full change log."},
        {"threat": "CSV/formula injection when opened in Excel", "mitigation": "Production: prefix cells starting with = + - @ with a quote on export."},
        {"threat": "PII in sample values sent to a model", "mitigation": "Profile sends at most 6 samples per column; mask or omit samples for PII columns."},
    ],
    "cost_latency": "Profile JSON is ~150 tokens per column regardless of row count; one model call. Execution is linear in cells.",
    "failure_modes": [
        {"mode": "Ambiguous D/M vs M/D dates", "mitigation": "Day-first inference from values >12; otherwise explicit assumption in notes."},
        {"mode": "Over-aggressive deduplication", "mitigation": "Dedup keys are explicit and reported; flag instead of delete when unsure."},
        {"mode": "Type mis-inference on small samples", "mitigation": "Unparsed counts per operation reveal mismatches."},
    ],
    "improvements": ["Streaming for large files", "Great Expectations / dbt test export", "User-editable plan before apply", "Plan reuse per data source"],
    "production_checklist": ["Formula-injection-safe export", "Row/size limits", "Plan approval UI", "Original file retention"],
    "challenges": [
        {"level": "beginner", "title": "Phone numbers", "description": "Add a normalize_phone op (E.164) to the allowlist with tests."},
        {"level": "intermediate", "title": "Plan editing", "description": "Accept a user-edited plan and re-apply it without calling the model."},
        {"level": "advanced", "title": "Schema contracts", "description": "Accept a target JSON schema and report rows that still violate it after cleaning."},
    ],
    "interview_questions": [
        {"q": "Why let the model plan but not execute?", "a": "Planning needs judgement; execution needs determinism and auditability. Allowlisted ops bound what can happen."},
        {"q": "How do you handle ambiguous date formats?", "a": "Infer from impossible values (>12), otherwise make the assumption explicit and reviewable."},
        {"q": "When is this better done without an LLM?", "a": "For recurring feeds with stable schemas - codify the plan once."},
    ],
}
