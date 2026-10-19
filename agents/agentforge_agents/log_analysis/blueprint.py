BLUEPRINT = {
    "category": "Developer Productivity",
    "level": "intermediate",
    "build_hours": 5,
    "tags": ["observability", "sre", "incident-response", "logs"],
    "summary": "Parses raw logs, clusters errors into templates, detects spikes and deploy correlation, then drafts ranked root-cause hypotheses.",
    "problem": "During incidents, engineers scroll through thousands of log lines to find which errors matter, when they started and whether a deploy caused them.",
    "business_value": "Reduces time-to-first-hypothesis during incidents and standardises triage notes. The deterministic statistics are useful even without any model.",
    "inputs": ["Raw log text: JSON lines or `TIMESTAMP LEVEL [service] message`", "Optional service name filter"],
    "outputs": ["Error clusters with counts, first/last seen, sample and stack hint", "Per-minute error histogram and spikes",
                "Deploy markers and cluster↔deploy correlations", "Severity estimate and 1-4 hypotheses citing cluster ids"],
    "prerequisites": ["Regular expressions", "Basic statistics (median, standard deviation)", "Incident response basics"],
    "verdict": "workflow",
    "verdict_reasoning": "Parsing, templating, clustering and spike detection are deterministic and must be reproducible. "
                         "The only judgement call - turning evidence into hypotheses - is one structured model call. "
                         "An autonomous agent that 'reads logs' would be slower, costlier and would miss counts.",
    "architecture_mermaid": """flowchart LR
    L[Raw logs] --> P[parse_logs]
    P --> T[template + cluster]
    P --> H[error histogram]
    H --> S[spike detection]
    P --> D[deploy markers]
    T --> X[correlate with deploys]
    D --> X
    T & S & X --> M[LLM: hypotheses]
    M --> G{evidence guardrail}
    G --> R[Report]""",
    "data_flow": [
        "Lines are parsed (JSON or text); stack-trace continuation lines attach to the previous event.",
        "Variable parts (UUIDs, IPs, numbers, hex ids) are replaced with tokens so similar messages share a template.",
        "WARN+ events are grouped by (level, template); ERROR events feed a per-minute histogram.",
        "Spikes = minutes above max(5, mean + 2σ, 3×median). Deploy markers are matched against cluster first-seen times.",
        "Model returns hypotheses that must cite existing cluster ids; unsupported 'high confidence' claims are downgraded.",
    ],
    "framework": {"choice": "Plain Python", "reasoning": "Linear pipeline with one model call. A log platform (Loki, CloudWatch Logs Insights, Elastic) would replace parse/cluster at scale."},
    "model_selection": {"recommended": "Mid-size model with good reasoning over structured JSON.",
                        "reasoning": "The model sees summaries, not raw logs, so context stays small; hypothesis quality benefits from stronger reasoning.",
                        "alternatives": ["Small model for routine alerts", "Mock provider for offline demos"]},
    "state_memory": "Stateless. In production, persist clusters per incident so follow-up runs can diff 'new since last run'.",
    "security": [
        {"threat": "Secrets/PII in logs sent to a model", "mitigation": "Only templates and samples are sent; add redaction before the model call; prefer self-hosted models for regulated data."},
        {"threat": "Prompt injection via log messages (attacker-controlled user agents, paths)", "mitigation": "Clusters are fenced as untrusted data; the model has no tools, so injection cannot trigger actions."},
        {"threat": "Huge inputs causing memory pressure", "mitigation": "Input size limit and max line count; stream parse for production."},
    ],
    "cost_latency": "Model input is bounded by top-15 clusters (~2-4k tokens) regardless of log volume, so cost is roughly constant per run. Parsing 50k lines takes well under a second.",
    "failure_modes": [
        {"mode": "Unknown log format", "mitigation": "Falls back to keyword level detection; add a format adapter."},
        {"mode": "Over-templating merges distinct errors", "mitigation": "Tune variable patterns; keep the error class in the template."},
        {"mode": "Correlation mistaken for causation", "mitigation": "Hypotheses carry confidence and explicit next steps; never auto-rollback."},
    ],
    "improvements": ["Pull logs directly from CloudWatch/Loki with time-range tools", "Compare against a baseline window",
                     "Attach traces and metrics", "Feed confirmed root causes back as labelled eval cases"],
    "production_checklist": ["PII redaction before model calls", "Input size limits", "Incident-scoped persistence", "On-call feedback buttons"],
    "challenges": [
        {"level": "beginner", "title": "New format", "description": "Support nginx access logs and count 5xx responses per minute."},
        {"level": "intermediate", "title": "Baseline diff", "description": "Accept a baseline log and report clusters that are new or grew >3×."},
        {"level": "advanced", "title": "Tool-using investigator", "description": "Turn this into a LangGraph agent that can query logs by time range and service, with a step budget."},
    ],
    "interview_questions": [
        {"q": "Why template log messages before sending them to a model?", "a": "It compresses thousands of lines into a few patterns with counts, reducing cost and preventing the model from miscounting."},
        {"q": "How do you detect an error spike robustly?", "a": "Compare each window to robust statistics of the series (median, mean+kσ) with a minimum absolute floor."},
        {"q": "What is the risk of auto-remediation from this output?", "a": "Hypotheses are uncertain; correlation is not causation. Remediation should require human approval."},
    ],
}
