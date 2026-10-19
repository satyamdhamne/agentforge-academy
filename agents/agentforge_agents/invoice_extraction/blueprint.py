BLUEPRINT = {
    "category": "Finance Operations",
    "level": "intermediate",
    "build_hours": 5,
    "tags": ["document-ai", "extraction", "validation", "accounts-payable"],
    "summary": "Extracts invoice fields and line items into a schema, then validates arithmetic and grounding to decide auto-approve vs human review.",
    "problem": "Accounts-payable teams retype invoice data from PDFs; errors in totals or due dates cause late fees and reconciliation work.",
    "business_value": "Straight-through processing for clean invoices, with every exception explained so reviewers fix only what is wrong.",
    "inputs": ["Invoice text (OCR or PDF text layer)"],
    "outputs": ["Structured invoice (vendor, number, dates, currency, line items, subtotal, tax, total)",
                "Normalised ISO dates", "Validation issues with severity", "Status: auto_approved | needs_review"],
    "prerequisites": ["Structured outputs", "Regular expressions", "Floating-point money pitfalls"],
    "verdict": "workflow",
    "verdict_reasoning": "Extraction is one model call; correctness comes from validation, not from more model reasoning. "
                         "For a few high-volume vendors with fixed layouts, templates or a dedicated document-AI service are cheaper and more accurate.",
    "architecture_mermaid": """flowchart LR
    I[Invoice text] --> R[regex candidates]
    I --> L[LLM: extract → schema]
    R --> L
    L --> V{validate}
    I --> V
    V -->|math ok + grounded| A[auto_approved]
    V -->|any error| H[needs_review + issues]""",
    "data_flow": [
        "Regex finds candidate invoice number, dates, currency, labelled amounts and table-like line items.",
        "The model extracts into a strict schema, using candidates as hints and null for missing values.",
        "Validation: required fields, qty × unit = amount, Σ lines = subtotal, subtotal + tax = total, due ≥ issue date.",
        "Grounding: invoice number and amounts must literally appear in the source text.",
    ],
    "framework": {"choice": "Plain Python + Pydantic", "reasoning": "Extraction + validation. The validation layer is the product."},
    "model_selection": {"recommended": "Mid-size model with reliable JSON; vision model if you start from images.",
                        "reasoning": "Layout understanding helps; arithmetic is done in code, never by the model.",
                        "alternatives": ["Cloud document AI (Textract, Document AI)", "Vendor templates for top suppliers"]},
    "state_memory": "Stateless. Production: vendor master data lookup to validate vendor names and bank details.",
    "security": [
        {"threat": "Invoice fraud (changed bank details, inflated totals)", "mitigation": "Never auto-pay on extraction alone; match against PO and vendor master; flag changed bank details."},
        {"threat": "Prompt injection in invoice text", "mitigation": "Document fenced as untrusted; outputs validated against the source."},
        {"threat": "Float rounding errors", "mitigation": "Round to 2 decimals and compare with tolerance; use Decimal in production ledgers."},
    ],
    "cost_latency": "≈1 token per 4 characters of invoice text + ~600 for schema and prompt; one call per invoice.",
    "failure_modes": [
        {"mode": "Multi-page tables split across pages", "mitigation": "Concatenate pages before extraction; validate totals."},
        {"mode": "Ambiguous date formats (03/04/2026)", "mitigation": "Use vendor locale; flag for review when ambiguous."},
        {"mode": "Model computes a missing total", "mitigation": "Grounding check: amounts must appear in the source."},
    ],
    "improvements": ["Purchase-order matching (3-way match)", "Vendor master validation", "Image input via vision model", "Decimal-based money types"],
    "production_checklist": ["Human review queue", "PO matching", "Audit trail of edits", "Duplicate invoice detection by vendor+number"],
    "challenges": [
        {"level": "beginner", "title": "Discounts", "description": "Support a 'Discount' line and include it in the total check."},
        {"level": "intermediate", "title": "Duplicate detection", "description": "Flag invoices whose vendor + invoice number was seen before."},
        {"level": "advanced", "title": "PO match", "description": "Given a purchase order JSON, implement a 2-way match with per-line tolerance and explain mismatches."},
    ],
    "interview_questions": [
        {"q": "Why validate arithmetic in code rather than asking the model to check totals?", "a": "Models are unreliable at arithmetic; code is exact and explains failures precisely."},
        {"q": "What is a grounding check in extraction?", "a": "Verifying that extracted values literally exist in the source document, which catches hallucinated values."},
    ],
}
