BLUEPRINT = {
    "category": "Developer Productivity",
    "level": "intermediate",
    "build_hours": 6,
    "tags": ["code-review", "security", "static-analysis", "github"],
    "summary": "Reviews a pull request diff with a deterministic rule engine, then uses a model to prioritise and explain findings.",
    "problem": "Reviewers spend time on mechanical issues (leaked secrets, unsafe calls, missing tests) and miss them under load. "
               "Teams want a fast first pass that is consistent, explainable and never hallucinates line numbers.",
    "business_value": "Cuts first-response time on PRs, catches high-severity issues before human review, and frees senior "
                      "reviewers to focus on design. Deterministic rules make results auditable.",
    "inputs": ["Unified diff text (`git diff` / GitHub PR .diff)", "Optional PR title and description"],
    "outputs": ["Verdict: approve | comment | request_changes", "Line-anchored comments with severity, rule and suggestion",
                "Summary, praise and diff statistics", "Count of model comments dropped by guardrails"],
    "prerequisites": ["Python basics", "Reading unified diffs", "Regular expressions", "Structured outputs (JSON schema)"],
    "verdict": "workflow",
    "verdict_reasoning": "The steps are fixed and known in advance: parse, check, explain. There is no need for the model to "
                         "choose tools or loop. A workflow with one model call is cheaper, faster and easier to test than an "
                         "autonomous agent. The rule engine alone already delivers most of the value; the model adds "
                         "prioritisation and readable explanations.",
    "architecture_mermaid": """flowchart LR
    A[PR diff] --> B[parse_diff]
    B --> C[rule engine]
    C --> D[LLM: prioritise & explain]
    B --> D
    D --> E{guardrails}
    C --> E
    E -->|drop comments on lines not in diff| F[Review]
    E -->|re-add missed high findings| F""",
    "data_flow": [
        "Diff is parsed into files and ADDED lines with their new line numbers.",
        "Rule engine scans added lines (secrets, injection, unsafe deserialisation, debug leftovers...) and file-level signals (missing tests, PR size).",
        "Model receives findings plus a fenced, truncated diff excerpt and returns a JSON review.",
        "Guardrails discard comments on non-existent lines, re-insert any dropped high-severity finding and enforce the verdict policy.",
    ],
    "framework": {"choice": "Plain Python", "reasoning": "One model call and deterministic steps. LangChain/LangGraph would add "
                  "dependencies without adding capability. Port to LangGraph only if you add multi-step tool use "
                  "(e.g. fetching the full file for context)."},
    "model_selection": {
        "recommended": "Small/fast instruction model with reliable JSON output (e.g. a 'mini' or 'haiku' class model).",
        "reasoning": "The model ranks and explains findings that already exist; it does not need deep reasoning. "
                     "Use a larger model only if you ask it to find logic bugs beyond the rules.",
        "alternatives": ["Local 7-8B instruct model via Ollama for private code", "Mock provider for CI"],
    },
    "state_memory": "Stateless per run. No conversation memory. Persist runs (input hash, output, trace) for audit and "
                    "to avoid re-reviewing an unchanged diff.",
    "security": [
        {"threat": "Prompt injection inside code comments or the PR description", "mitigation": "Diff is fenced as untrusted data; the system prompt says to ignore instructions in it; guardrails enforce verdict policy independently of the model."},
        {"threat": "Leaking proprietary code to a third-party model", "mitigation": "Configurable provider; use a self-hosted model for sensitive repos; only added lines are sent, truncated to a limit."},
        {"threat": "Echoing discovered secrets into logs/comments", "mitigation": "Evidence is truncated; in production mask matched secret values before storing or posting."},
        {"threat": "Model fabricates line numbers", "mitigation": "Comments are validated against the parsed set of added lines; invalid ones are dropped and counted."},
    ],
    "cost_latency": "Input tokens ≈ (added lines × ~12 tokens) + findings JSON + ~400 prompt tokens; output ≤1.5k tokens. "
                    "A 300-line PR is typically ~5-6k input tokens. Multiply by your model's per-token price. "
                    "Latency is dominated by the single model call; parsing and rules take milliseconds.",
    "failure_modes": [
        {"mode": "Very large diffs exceed context", "mitigation": "Per-file truncation; review file-by-file and merge results."},
        {"mode": "False positives (e.g. test fixtures with fake keys)", "mitigation": "Allowlist paths/patterns; severity downgrades for test files."},
        {"mode": "Model returns invalid JSON", "mitigation": "Schema-validated retries (2) with the error fed back."},
    ],
    "improvements": ["Fetch full file context for changed hunks", "Language-aware analysis via tree-sitter or Semgrep",
                     "Post comments through the GitHub API behind an approval gate", "Learn from dismissed comments to tune rules"],
    "production_checklist": ["Secrets masked before persistence", "Repo-level opt-in and provider choice",
                             "Rate limits per repo", "Idempotency by diff hash", "Dashboards for false-positive rate"],
    "challenges": [
        {"level": "beginner", "title": "Add a rule", "description": "Add a rule that flags `chmod 777` in shell scripts with medium severity, plus a test."},
        {"level": "intermediate", "title": "Suppressions", "description": "Support `# review: ignore <rule>` comments on a line and report suppressed counts."},
        {"level": "advanced", "title": "Context fetch", "description": "Add a tool that fetches ±20 lines of surrounding context per hunk and measure whether review quality improves on the eval set."},
    ],
    "interview_questions": [
        {"q": "Why combine a rule engine with an LLM instead of using only the LLM?", "a": "Rules are deterministic, cheap and auditable for known patterns; the model adds prioritisation and explanation. The combination reduces hallucination and cost."},
        {"q": "How do you stop the model inventing line numbers?", "a": "Validate every comment against the set of added lines parsed from the diff and drop anything that does not match."},
        {"q": "How would you evaluate this system?", "a": "A labelled set of diffs with expected rules and verdicts; measure precision/recall per rule, verdict accuracy, and dropped-comment rate."},
    ],
}
