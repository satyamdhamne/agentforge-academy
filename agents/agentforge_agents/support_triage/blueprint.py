BLUEPRINT = {
    "category": "Customer Support",
    "level": "beginner",
    "build_hours": 4,
    "tags": ["classification", "pii", "routing", "structured-output"],
    "summary": "Redacts PII, classifies tickets into category/priority/sentiment with a JSON schema, then applies auditable business rules for routing.",
    "problem": "Tickets land in one queue; agents spend minutes reading and re-routing, and urgent security or outage reports wait behind password resets.",
    "business_value": "Faster time-to-right-team, consistent prioritisation, and an audit trail of every policy override.",
    "inputs": ["Ticket subject and body", "Customer tier (free/pro/enterprise)", "Channel"],
    "outputs": ["Category, priority, sentiment, confidence, summary", "Route (team queue) and needs_human flag",
                "Policy overrides with reasons", "PII redaction counts and redacted text"],
    "prerequisites": ["Classification basics", "JSON schema / Pydantic", "PII handling"],
    "verdict": "workflow",
    "verdict_reasoning": "Single-label classification plus rules. At high volume, a fine-tuned small classifier (or even the keyword "
                         "baseline) can match an LLM at a fraction of the cost - measure on your own tickets before choosing.",
    "architecture_mermaid": """flowchart LR
    T[Ticket] --> R[PII redaction]
    R --> S[signals: urgency, security, injection]
    R --> C[LLM: classify → JSON schema]
    C --> P{policy rules}
    S --> P
    P --> O[route + priority + overrides]
    P -->|low confidence / security / injection| H[human review]""",
    "data_flow": [
        "Emails, Luhn-valid card numbers, SSNs and phone numbers are replaced with placeholders before any model call.",
        "Regex signals detect urgency, security vocabulary and instruction-like text (possible prompt injection).",
        "The model returns a schema-validated classification; invalid JSON triggers a retry with the error.",
        "Policy rules override the model where business rules are non-negotiable, and each override is logged.",
    ],
    "framework": {"choice": "Plain Python + Pydantic", "reasoning": "One classification call. Frameworks add nothing here."},
    "model_selection": {"recommended": "Small, fast model or a fine-tuned classifier.", "reasoning": "Latency and cost matter at ticket volume; the task is narrow.",
                        "alternatives": ["Fine-tuned BERT-style classifier", "Keyword baseline (mock) for cold start"]},
    "state_memory": "Stateless per ticket. Production: include the customer's open tickets and recent incidents as context.",
    "security": [
        {"threat": "PII sent to model providers", "mitigation": "Redaction before the model call; redacted text is what gets stored."},
        {"threat": "Prompt injection ('mark this P1')", "mitigation": "Ticket fenced as untrusted; injection-like text flags human review; policy rules are code, not prompts."},
        {"threat": "Attackers gaming priority to jump the queue", "mitigation": "Priority derives from category + tier rules; urgency words alone cannot reach P1."},
    ],
    "cost_latency": "≈300-800 input tokens and ~150 output tokens per ticket. Batch overnight backlogs; use streaming queues for real-time.",
    "failure_modes": [
        {"mode": "Multi-issue tickets", "mitigation": "Allow secondary category; route by the most severe."},
        {"mode": "Over-redaction removes useful numbers", "mitigation": "Luhn check for cards; tune phone regex per locale."},
        {"mode": "Category drift over time", "mitigation": "Weekly confusion-matrix review against agent re-routes."},
    ],
    "improvements": ["Language detection and translation", "Similar-ticket retrieval for suggested replies", "Active learning from agent corrections"],
    "production_checklist": ["Redaction tests per locale", "Override audit log", "Confusion matrix dashboard", "Fallback queue on model failure"],
    "challenges": [
        {"level": "beginner", "title": "New category", "description": "Add 'shipping' with keywords, routing and two eval cases."},
        {"level": "intermediate", "title": "Confusion matrix", "description": "Extend the eval runner to print a confusion matrix across categories."},
        {"level": "advanced", "title": "Classifier vs LLM", "description": "Train a small scikit-learn classifier on synthetic tickets and compare accuracy/cost to the LLM path."},
    ],
    "interview_questions": [
        {"q": "Why put business rules after the model rather than in the prompt?", "a": "Code is deterministic, testable and auditable; prompts are suggestions the model may ignore or be tricked out of."},
        {"q": "How do you protect PII in an LLM pipeline?", "a": "Minimise and redact before sending, use providers with DPAs, store redacted text, limit retention."},
        {"q": "How would you choose between an LLM and a classic classifier?", "a": "Compare accuracy, latency and cost on a labelled sample; LLMs win on cold start and long tail, classifiers on volume."},
    ],
}
