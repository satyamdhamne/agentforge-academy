"""Tiny, safe template rendering: {{name}} and {{path.to.value}} only. No code execution, no filters."""

from __future__ import annotations

import json
import re
from typing import Any

from ..core.errors import AppError

VAR = re.compile(r"{{\s*([A-Za-z_][\w.\-]*)\s*}}")


def variables(template: str) -> list[str]:
    seen: list[str] = []
    for m in VAR.finditer(template or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def lookup(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def render(template: str, data: dict[str, Any], strict: bool = True) -> str:
    missing: list[str] = []

    def repl(m: re.Match) -> str:
        try:
            v = lookup(data, m.group(1))
        except KeyError:
            missing.append(m.group(1))
            return ""
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    out = VAR.sub(repl, template or "")
    if strict and missing:
        raise AppError(f"Missing template variable(s): {', '.join(sorted(set(missing)))}", code="missing_variables",
                       status_code=422, details=sorted(set(missing)))
    return out
