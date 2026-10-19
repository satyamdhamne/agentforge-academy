BLUEPRINT = {
    "category": "Developer Productivity",
    "level": "beginner",
    "build_hours": 3,
    "tags": ["release-management", "conventional-commits", "deterministic-first"],
    "summary": "Groups Conventional Commits into release notes deterministically; optionally rewrites customer-facing items in plain language with traceable ids.",
    "problem": "Release notes are written by hand at the last minute, miss changes, or leak internal jargon to customers.",
    "business_value": "Consistent notes on every release in seconds; customer notes stay accurate because each line maps to a real commit.",
    "inputs": ["Commit subjects (git log --oneline)", "Version and previous version", "Audience: developers or customers", "Release date"],
    "outputs": ["Markdown release notes", "Sections by change type", "Highlights (customers)", "Dropped and fallback item ids"],
    "prerequisites": ["Conventional Commits", "Semantic versioning", "Regular expressions"],
    "verdict": "deterministic",
    "verdict_reasoning": "This is the clearest 'you don't need an agent' case in the library. Developer notes are a pure script "
                         "(the model is never called). The model is an optional polishing step for customer-facing wording, "
                         "constrained so it cannot add, drop or merge changes.",
    "architecture_mermaid": """flowchart LR
    G[git log] --> P[parse Conventional Commits]
    P --> S[group into sections]
    S -->|developers| M[render markdown]
    S -->|customers| L[LLM: plain-language rewrite by id]
    L --> V{id check}
    V -->|unknown ids dropped| M
    V -->|missing ids → original text| M""",
    "data_flow": [
        "Each line is parsed as type(scope)!: description with optional hash and PR refs; others are 'Maintenance'.",
        "Breaking (`!` or BREAKING CHANGE) and security-flavoured fixes are promoted to their own sections.",
        "Developers: rendered directly with scopes, PR numbers and short hashes.",
        "Customers: only user-facing sections go to the model; each returned item must reference a real id.",
    ],
    "framework": {"choice": "Plain Python", "reasoning": "A parser and a template. Adding a framework would be over-engineering."},
    "model_selection": {"recommended": "Small model, only for the customer audience.", "reasoning": "Short rewriting task with strict structure.",
                        "alternatives": ["No model at all - enforce good commit messages instead"]},
    "state_memory": "Stateless. In CI, store the notes artifact per tag.",
    "security": [
        {"threat": "Internal details leaking into public notes", "mitigation": "Only user-facing sections are sent for rewrite; maintenance commits are never published to customers."},
        {"threat": "Model inventing features", "mitigation": "Items must carry existing ids; unknown ids are dropped and reported."},
    ],
    "cost_latency": "Developers: zero model cost. Customers: ~30 tokens per commit in, ~25 out.",
    "failure_modes": [
        {"mode": "Non-conventional commit messages", "mitigation": "They land in Maintenance; enforce commitlint in CI."},
        {"mode": "Model skips an item", "mitigation": "Fallback to original description so nothing is lost."},
    ],
    "improvements": ["Pull commits between tags via the GitHub API", "Link PRs and authors", "Publish to a changelog page via CI"],
    "production_checklist": ["commitlint in CI", "Human approval before publishing customer notes", "Notes stored per tag"],
    "challenges": [
        {"level": "beginner", "title": "Contributors", "description": "Parse `(author)` suffixes and list contributors at the end."},
        {"level": "intermediate", "title": "Semver check", "description": "Warn if a breaking change exists but the version is not a major bump."},
        {"level": "advanced", "title": "GitHub Action", "description": "Package this as a GitHub Action that comments draft notes on release PRs."},
    ],
    "interview_questions": [
        {"q": "When should you avoid using an LLM for a task like this?", "a": "When inputs are structured and the transformation is rule-based - a script is cheaper, faster and exact."},
        {"q": "How do you stop a model from adding things that didn't happen?", "a": "Give each source item an id, require ids in the output, and drop anything that doesn't map back."},
    ],
}
