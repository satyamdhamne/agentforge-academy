"""Tiny evaluation harness.

Each agent ships `evals/cases.jsonl`; every line is a case:

    {"id": "secret-in-config", "input": {...}, "checks": [{"type": "equals", "path": "verdict", "value": "request_changes"}]}

Check types
-----------
equals, not_equals, in (values), contains (list/str contains value), not_contains, len_gte, len_lte,
gte, lte, approx (value, tol), truthy, falsy, regex (pattern).

Paths use dots and `[*]` to map over lists, e.g. `comments[*].rule`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core import LLMProvider, run_agent
from .core.spec import AgentSpec

_MISSING = object()


def resolve(obj: Any, path: str) -> Any:
    if path in ("", "$"):
        return obj
    parts = re.findall(r"[^.\[\]]+|\[\*\]", path)
    values = [obj]
    mapped = False
    for part in parts:
        nxt = []
        for v in values:
            if part == "[*]":
                mapped = True
                nxt.extend(v if isinstance(v, list) else [])
            elif isinstance(v, dict):
                nxt.append(v.get(part, _MISSING))
            elif isinstance(v, list) and part.isdigit() and int(part) < len(v):
                nxt.append(v[int(part)])
            else:
                nxt.append(_MISSING)
        values = nxt
    values = [v for v in values if v is not _MISSING] if mapped else values
    if mapped:
        return values
    return None if values[0] is _MISSING else values[0]


def evaluate_check(output: Any, check: dict) -> tuple[bool, str]:
    t, actual = check["type"], resolve(output, check.get("path", ""))
    exp = check.get("value")
    ok: bool
    if t == "equals":
        ok = actual == exp
    elif t == "not_equals":
        ok = actual != exp
    elif t == "in":
        ok = actual in check["values"]
    elif t == "contains":
        ok = actual is not None and exp in actual
    elif t == "not_contains":
        ok = actual is None or exp not in actual
    elif t == "len_gte":
        ok = actual is not None and len(actual) >= exp
    elif t == "len_lte":
        ok = actual is not None and len(actual) <= exp
    elif t == "gte":
        ok = actual is not None and actual >= exp
    elif t == "lte":
        ok = actual is not None and actual <= exp
    elif t == "approx":
        ok = actual is not None and abs(actual - exp) <= check.get("tol", 0.01)
    elif t == "truthy":
        ok = bool(actual)
    elif t == "falsy":
        ok = not actual
    elif t == "regex":
        ok = actual is not None and re.search(check["pattern"], str(actual)) is not None
    else:
        raise ValueError(f"unknown check type {t}")
    desc = f"{t} {check.get('path', '')} expected={exp if exp is not None else check.get('values', check.get('pattern'))!r} actual={str(actual)[:120]!r}"
    return ok, desc


@dataclass
class CaseResult:
    id: str
    passed: bool
    status: str
    checks: list[dict] = field(default_factory=list)
    error: str | None = None


def load_cases(spec: AgentSpec) -> list[dict]:
    pkg_dir = Path(__import__(spec.package, fromlist=["_"]).__file__).parent
    path = pkg_dir / "evals" / "cases.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_eval(spec: AgentSpec, provider: LLMProvider | None = None, sandbox=None) -> dict:
    results: list[CaseResult] = []
    for case in load_cases(spec):
        r = run_agent(spec, case["input"], provider=provider, sandbox=sandbox, user_groups=case.get("user_groups"))
        if r.output is None:
            results.append(CaseResult(case["id"], False, r.status, error=r.error))
            continue
        checks = []
        for c in case.get("checks", []):
            ok, desc = evaluate_check({**r.output, "__status": r.status}, c)
            checks.append({"passed": ok, "check": desc})
        results.append(CaseResult(case["id"], all(c["passed"] for c in checks), r.status, checks))
    passed = sum(r.passed for r in results)
    return {
        "agent": spec.slug,
        "cases": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 3) if results else None,
        "results": [r.__dict__ for r in results],
    }
