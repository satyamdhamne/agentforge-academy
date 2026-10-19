BLUEPRINT = {
    "category": "Developer Productivity",
    "level": "intermediate",
    "build_hours": 6,
    "tags": ["testing", "pytest", "ast", "sandbox"],
    "summary": "Analyses Python functions with the AST, generates pytest tests, rejects unsafe tests statically and runs the rest in an isolated sandbox.",
    "problem": "Legacy and fast-moving code lacks tests; writing the first round of tests is tedious, and generated tests often don't even run.",
    "business_value": "Bootstraps a test suite quickly while proving each test executes. Unsafe or broken tests never reach the repo.",
    "inputs": ["Python module source", "Module name for imports", "Max tests per function"],
    "outputs": ["Accepted tests and a ready-to-save test file", "Rejected tests with reasons", "Sandbox execution results (passed/failed/errors)"],
    "prerequisites": ["pytest basics", "Python AST module", "Why untrusted code needs a sandbox"],
    "verdict": "workflow",
    "verdict_reasoning": "Analysis, generation, validation and execution happen in a fixed order. The model does creative work in one step; "
                         "everything around it is deterministic. A loop that 'fixes failing tests' is a tempting extension, but it can "
                         "silently change assertions to match buggy code - so failures are reported to a human instead.",
    "architecture_mermaid": """flowchart LR
    S[Source] --> A[AST analysis]
    A --> G[LLM: generate tests]
    G --> V{static validation}
    V -->|reject| X[rejected list]
    V -->|accept| B[build script + pytest shim]
    B --> SB[[Isolated sandbox]]
    SB --> R[Results + test file]""",
    "data_flow": [
        "AST extracts public functions, parameters, type hints, docstring examples, explicit raise conditions and a complexity score.",
        "The model writes tests; each is parsed and checked: one test_* function, only pytest/math imports, no file/eval/dunder access.",
        "Accepted tests plus a tiny pytest shim are executed in the sandbox service (no network, CPU/memory/time limits).",
        "Without a sandbox, tests are statically validated only and clearly marked 'not_run'.",
    ],
    "framework": {"choice": "Plain Python", "reasoning": "Linear pipeline. The interesting engineering is AST analysis and the sandbox boundary, not orchestration."},
    "model_selection": {"recommended": "Strong code model.", "reasoning": "Test quality depends on reasoning about edge cases; volume is small.",
                        "alternatives": ["Property-based testing (Hypothesis) without a model", "Mutation testing to score generated tests"]},
    "state_memory": "Stateless. Store generated suites with the source hash to avoid regenerating unchanged modules.",
    "security": [
        {"threat": "Executing user-supplied source code", "mitigation": "Code only runs in the separate sandbox service with no network, read-only filesystem, resource limits and a non-root user - never in the API process."},
        {"threat": "Generated tests performing I/O or escaping", "mitigation": "Static AST validation rejects imports beyond pytest/math, eval/exec/open and dunder access."},
        {"threat": "Prompt injection in docstrings", "mitigation": "Source is fenced as untrusted; outputs are validated structurally; tests have no privileges anyway."},
    ],
    "cost_latency": "Input ≈ source tokens + analysis JSON (~1.3× source); output ≈ 150 tokens per test. Sandbox execution adds ~100-500 ms.",
    "failure_modes": [
        {"mode": "Tests assert current (buggy) behaviour", "mitigation": "Prefer docstring/spec-derived expectations; review before committing."},
        {"mode": "Flaky tests (time, randomness)", "mitigation": "Prompt forbids them; run twice and drop non-deterministic tests."},
        {"mode": "Imports of project-local modules", "mitigation": "Tests target a single module; extend with a dependency bundle for real projects."},
    ],
    "improvements": ["Mutation testing to score suites", "Coverage measurement in the sandbox", "Class and method support", "Hypothesis property tests"],
    "production_checklist": ["Sandbox isolation verified", "Static validation allowlist reviewed", "Human review before merge", "Flakiness detection"],
    "challenges": [
        {"level": "beginner", "title": "Boundary values", "description": "Extend the mock to also test the boundary value that does NOT raise."},
        {"level": "intermediate", "title": "Class support", "description": "Analyse classes and generate tests for public methods."},
        {"level": "advanced", "title": "Mutation score", "description": "Introduce simple mutants (flip comparisons) and report how many each generated suite kills."},
    ],
    "interview_questions": [
        {"q": "Why is executing generated tests inside your API server dangerous?", "a": "Tests import and run user code; that code can read secrets, call the network or exhaust resources. Isolation must be at the process/container level."},
        {"q": "Why not let the agent auto-fix failing tests?", "a": "It can rewrite assertions to match buggy behaviour, hiding real defects. Failures need human judgement."},
        {"q": "How would you measure generated test quality?", "a": "Execution pass rate, coverage, and mutation score - not test count."},
    ],
}
