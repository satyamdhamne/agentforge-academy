"""Deterministic output checks shared by the prompt lab, evaluations and the Agent Builder evaluation node."""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

from agentforge_agents.core import extract_json

TYPES = ("contains", "not_contains", "regex", "not_regex", "equals", "one_of", "json_valid", "json_schema",
         "max_words", "min_words", "max_chars")


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def check(assertion: dict[str, Any], output: Any) -> dict[str, Any]:
    kind = assertion.get("type")
    value = assertion.get("value")
    text = _as_text(output)
    passed = False
    detail = ""
    if kind == "contains":
        passed = str(value).lower() in text.lower()
    elif kind == "not_contains":
        passed = str(value).lower() not in text.lower()
    elif kind == "regex":
        passed = re.search(str(value), text, flags=re.M | re.I) is not None
    elif kind == "not_regex":
        passed = re.search(str(value), text, flags=re.M | re.I) is None
    elif kind == "equals":
        passed = text.strip().lower() == str(value).strip().lower()
    elif kind == "one_of":
        passed = text.strip().lower() in [str(v).strip().lower() for v in (value or [])]
    elif kind == "json_valid":
        passed = _parse_json(text) is not None
        detail = "" if passed else "Output is not valid JSON on its own (extra prose or code fences?)."
    elif kind == "json_schema":
        data = _parse_json(text)
        if data is None:
            detail = "Output is not valid JSON."
        else:
            try:
                jsonschema.validate(data, value or {})
                passed = True
            except jsonschema.ValidationError as exc:
                detail = f"Schema violation at {'/'.join(map(str, exc.absolute_path)) or 'root'}: {exc.message[:200]}"
    elif kind in ("max_words", "min_words"):
        n = len(text.split())
        passed = n <= int(value) if kind == "max_words" else n >= int(value)
        detail = f"{n} words"
    elif kind == "max_chars":
        passed = len(text) <= int(value)
        detail = f"{len(text)} characters"
    else:
        detail = f"Unknown assertion type '{kind}'."
    return {"type": kind, "value": value, "passed": passed, "detail": detail, "label": assertion.get("label") or describe(assertion)}


def describe(a: dict[str, Any]) -> str:
    k, v = a.get("type"), a.get("value")
    return {
        "contains": f"contains “{v}”", "not_contains": f"does not contain “{v}”", "regex": f"matches /{v}/",
        "not_regex": f"does not match /{v}/", "equals": f"equals “{v}”", "one_of": f"is one of {v}",
        "json_valid": "is valid JSON", "json_schema": "matches the JSON schema", "max_words": f"at most {v} words",
        "min_words": f"at least {v} words", "max_chars": f"at most {v} characters",
    }.get(str(k), str(k))


def run_checks(assertions: list[dict[str, Any]], output: Any) -> dict[str, Any]:
    results = [check(a, output) for a in assertions]
    passed = sum(r["passed"] for r in results)
    return {"results": results, "passed": passed, "total": len(results), "score": round(passed / len(results), 3) if results else 1.0}


def lenient_json(text: str) -> Any:
    """Parse JSON even when wrapped in prose or code fences (what a tolerant client would do)."""
    try:
        return extract_json(text)
    except Exception:  # noqa: BLE001 - any parse failure means "not JSON"
        return None
