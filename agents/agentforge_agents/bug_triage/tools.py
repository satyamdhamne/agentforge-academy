"""Demo issue tracker and the tools exposed to the Bug Triage agent.

The tracker is an in-memory fixture so the agent runs offline. Swap these functions for GitHub /
Jira API calls in production - the tool *contracts* (names, argument schemas) stay the same.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from ..core import Tool, ToolRegistry
from ..core.text import TfidfIndex

NOW = datetime(2026, 3, 12, 9, 0)

ISSUES = [
    {"id": "BUG-101", "title": "Checkout fails with KeyError 'currency' for guest users", "component": "checkout", "status": "open",
     "labels": ["bug", "checkout"], "body": "KeyError: 'currency' in checkout/pricing.py when guest has no profile."},
    {"id": "BUG-102", "title": "Search results empty when query contains apostrophe", "component": "search", "status": "closed",
     "labels": ["bug", "search"], "body": "Queries like O'Brien return nothing; escaping issue in query builder."},
    {"id": "BUG-103", "title": "PDF export times out for reports over 50 pages", "component": "reports", "status": "open",
     "labels": ["bug", "performance", "reports"], "body": "Export worker hits the 30s timeout for large reports."},
    {"id": "BUG-104", "title": "Login loop after password reset on Safari", "component": "auth", "status": "open",
     "labels": ["bug", "auth"], "body": "After reset, Safari users are redirected back to login repeatedly. Cookie SameSite issue suspected."},
    {"id": "BUG-105", "title": "Avatar upload rejects PNG files larger than 1MB", "component": "profile", "status": "closed",
     "labels": ["bug", "profile"], "body": "Validation limit is wrong; should be 5MB."},
    {"id": "BUG-106", "title": "Duplicate charge when user double-clicks Pay", "component": "checkout", "status": "open",
     "labels": ["bug", "checkout", "payments"], "body": "No idempotency key on payment submission; double click charges twice."},
    {"id": "BUG-107", "title": "Notifications not delivered for mentions in comments", "component": "notifications", "status": "open",
     "labels": ["bug", "notifications"], "body": "Mention parser misses usernames with dots."},
    {"id": "BUG-108", "title": "TypeError in pricing when discount code is expired", "component": "checkout", "status": "closed",
     "labels": ["bug", "checkout"], "body": "TypeError: unsupported operand NoneType in checkout/pricing.py apply_discount."},
]
COMPONENTS = {
    "checkout": {"team": "payments-team", "owners": ["@lena", "@omar"], "oncall": "@omar"},
    "search": {"team": "discovery-team", "owners": ["@hiro"], "oncall": "@hiro"},
    "reports": {"team": "insights-team", "owners": ["@priya"], "oncall": "@priya"},
    "auth": {"team": "identity-team", "owners": ["@sara", "@ben"], "oncall": "@ben"},
    "profile": {"team": "identity-team", "owners": ["@sara"], "oncall": "@ben"},
    "notifications": {"team": "platform-team", "owners": ["@kofi"], "oncall": "@kofi"},
}
DEPLOYS = [
    {"component": "checkout", "version": "checkout@3.8.0", "at": (NOW - timedelta(hours=5)).isoformat(),
     "summary": "Refactor pricing for multi-currency"},
    {"component": "auth", "version": "auth@2.2.1", "at": (NOW - timedelta(hours=60)).isoformat(), "summary": "Session cookie hardening"},
    {"component": "search", "version": "search@5.0.0", "at": (NOW - timedelta(hours=20)).isoformat(), "summary": "New ranking model"},
]
ALLOWED_LABELS = {"bug", "regression", "duplicate", "needs-info", "performance", "security", "payments", "ux",
                  "severity:critical", "severity:high", "severity:medium", "severity:low", *COMPONENTS}

_index = TfidfIndex({i["id"]: f"{i['title']} {i['body']}" for i in ISSUES})


class ParseStackTraceArgs(BaseModel):
    text: str = Field(..., max_length=20_000)


class SearchArgs(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(5, ge=1, le=10)


class ComponentArgs(BaseModel):
    component: str = Field(..., max_length=50)


class DeploysArgs(BaseModel):
    component: str = Field(..., max_length=50)
    hours: int = Field(48, ge=1, le=336)


class FinalizeArgs(BaseModel):
    severity: str = Field(..., pattern="^(critical|high|medium|low)$")
    component: str
    labels: list[str] = Field(default_factory=list, max_length=8)
    assignee_team: str
    duplicate_of: str | None = None
    summary: str = Field(..., max_length=500)
    reasoning: str = Field(..., max_length=2000)


class ApplyTriageArgs(BaseModel):
    labels: list[str]
    severity: str
    assignee_team: str
    duplicate_of: str | None = None
    comment: str = Field(..., max_length=4000)


def parse_stack_trace(text: str) -> dict:
    frames = []
    for m in re.finditer(r'File "([^"]+)", line (\d+), in (\w+)', text):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "function": m.group(3)})
    for m in re.finditer(r"at (?:(\S+) \()?([\w./-]+\.(?:js|ts|tsx)):(\d+)(?::\d+)?\)?", text):
        frames.append({"file": m.group(2), "line": int(m.group(3)), "function": m.group(1) or "<anonymous>"})
    exc = re.search(r"^\s*([A-Z]\w*(?:Error|Exception))(?::\s*(.*))?$", text, re.MULTILINE)
    component = None
    for f in reversed(frames):  # innermost application frame wins
        top = f["file"].lstrip("./").split("/")[0]
        if top in COMPONENTS:
            component = top
            break
    return {"found": bool(frames or exc), "exception": exc.group(1) if exc else None,
            "message": (exc.group(2) or "").strip()[:200] if exc else None, "frames": frames[-5:], "component": component}


def search_similar_issues(query: str, limit: int = 5) -> list[dict]:
    by_id = {i["id"]: i for i in ISSUES}
    return [{"id": i, "title": by_id[i]["title"], "status": by_id[i]["status"], "component": by_id[i]["component"],
             "score": round(s, 3)} for i, s in _index.search(query, limit)]


def get_component_owners(component: str) -> dict:
    if component not in COMPONENTS:
        return {"error": f"unknown component '{component}'", "known_components": sorted(COMPONENTS)}
    return {"component": component, **COMPONENTS[component]}


def get_recent_deploys(component: str, hours: int = 48) -> list[dict]:
    cutoff = NOW - timedelta(hours=hours)
    return [d for d in DEPLOYS if d["component"] == component and datetime.fromisoformat(d["at"]) >= cutoff]


def apply_triage(labels: list[str], severity: str, assignee_team: str, duplicate_of: str | None, comment: str) -> dict:
    """Side effect (demo): in production this calls the issue tracker API with a scoped token."""
    return {"applied": True, "tracker": "demo", "labels": labels, "severity": severity, "assigned_to": assignee_team,
            "duplicate_of": duplicate_of, "comment_posted": comment[:200]}


REGISTRY = ToolRegistry([
    Tool("parse_stack_trace", "Extract exception type, message, frames and likely component from a stack trace.", ParseStackTraceArgs, parse_stack_trace),
    Tool("search_similar_issues", "Search existing issues for likely duplicates or related reports.", SearchArgs, search_similar_issues),
    Tool("get_component_owners", "Look up the owning team, owners and on-call for a component.", ComponentArgs, get_component_owners),
    Tool("get_recent_deploys", "List deploys of a component within the last N hours.", DeploysArgs, get_recent_deploys),
    Tool("finalize_triage", "Submit the final triage decision. Call exactly once when you have enough evidence.", FinalizeArgs, lambda **kw: kw),
    Tool("apply_triage", "Apply labels/assignment and post a comment on the issue. Requires human approval.", ApplyTriageArgs, apply_triage, side_effect=True),
])
