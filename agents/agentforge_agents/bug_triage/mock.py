"""Offline *scripted policy* standing in for the model's tool choices.

It inspects which tools have already been called and their results, then picks the next tool -
mimicking what a model does in the loop. This keeps the agent loop, tool validation, budget and
approval gate fully testable without an API key. It is labelled 'mock' wherever runs are shown.
"""

from __future__ import annotations

import json
import re

from ..core import Completion, CompletionRequest, ToolCall, Usage, estimate_tokens
from .tools import COMPONENTS

KEYWORD_COMPONENT = {
    "checkout": ["checkout", "cart", "payment", "pay ", "charge", "pricing", "discount"],
    "auth": ["login", "log in", "password", "session", "sso", "2fa", "sign in"],
    "search": ["search", "query", "results"], "reports": ["report", "export", "pdf"],
    "notifications": ["notification", "email alert", "mention"], "profile": ["avatar", "profile"],
}


def _call(name: str, args: dict, n: int, prompt: str) -> Completion:
    return Completion(content="", tool_calls=[ToolCall(id=f"call_{n}_{name}", name=name, arguments=args)],
                      usage=Usage(estimate_tokens(prompt), 40), model="mock-1", provider="mock")


def step(request: CompletionRequest) -> Completion:
    issue = request.context["issue"]
    text = f"{issue['title']}\n{issue['body']}"
    results: dict[str, object] = {}
    for m in request.messages:
        if m.role == "tool" and m.name:
            results[m.name] = json.loads(m.content)
    n = len(results)
    prompt = "\n".join(m.content for m in request.messages)
    has_trace = bool(re.search(r'Traceback|File ".+", line \d+|\bat \S+:\d+', text))
    if has_trace and "parse_stack_trace" not in results:
        return _call("parse_stack_trace", {"text": issue["body"][:20000]}, n, prompt)
    trace = results.get("parse_stack_trace") or {}
    if "search_similar_issues" not in results:
        query = issue["title"] + (f" {trace.get('exception')} {trace.get('message') or ''}" if trace.get("exception") else "")
        return _call("search_similar_issues", {"query": query[:500], "limit": 5}, n, prompt)
    component = trace.get("component")
    if not component:
        low = text.lower()
        scores = {c: sum(low.count(k) for k in kws) for c, kws in KEYWORD_COMPONENT.items()}
        component = max(scores, key=scores.get) if any(scores.values()) else "unknown"
    if "get_component_owners" not in results and component in COMPONENTS:
        return _call("get_component_owners", {"component": component}, n, prompt)
    if "get_recent_deploys" not in results and component in COMPONENTS:
        return _call("get_recent_deploys", {"component": component, "hours": 48}, n, prompt)

    similar = results.get("search_similar_issues") or []
    deploys = results.get("get_recent_deploys") or []
    owners = results.get("get_component_owners") or {}
    low = text.lower()
    if re.search(r"data loss|charged twice|double charge|security|all users|cannot (pay|checkout)", low):
        severity = "critical"
    elif re.search(r"crash|500|error|exception|fails|broken|cannot", low):
        severity = "high"
    elif re.search(r"slow|sometimes|intermittent|workaround", low):
        severity = "medium"
    else:
        severity = "low"
    dup = next((s for s in similar if s["score"] >= 0.45 and s["status"] == "open" and s.get("component") == component), None)
    labels = ["bug"] + ([component] if component in COMPONENTS else ["needs-info"])
    if deploys:
        labels.append("regression")
    if dup:
        labels.append("duplicate")
    if "payment" in low or "charge" in low:
        labels.append("payments")
    reasoning = []
    if trace.get("exception"):
        reasoning.append(f"Stack trace shows {trace['exception']} in {component} code.")
    if deploys:
        reasoning.append(f"{deploys[0]['version']} was deployed at {deploys[0]['at']} ('{deploys[0]['summary']}'), suggesting a regression.")
    if dup:
        reasoning.append(f"{dup['id']} ('{dup['title']}') looks like the same failure (similarity {dup['score']}).")
    elif similar:
        reasoning.append(f"Closest existing issue is {similar[0]['id']} (similarity {similar[0]['score']}), not a clear duplicate.")
    args = {"severity": severity, "component": component, "labels": labels,
            "assignee_team": owners.get("team", "triage-queue"), "duplicate_of": dup["id"] if dup else None,
            "summary": f"{issue['title']} - {severity} severity in {component}.",
            "reasoning": " ".join(reasoning) or "Limited evidence; routed by keywords."}
    return _call("finalize_triage", args, n, prompt)


RESPONDERS = {"bug_triage.step": step}
