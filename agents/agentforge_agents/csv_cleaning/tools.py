"""CSV profiling and an allowlisted set of deterministic cleaning operations."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import datetime
from typing import Any

NULL_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-", "--", "?", "missing"}
_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d*\.\d+$|^-?\d+\.\d*$")
_FORMATTED_NUM = re.compile(r"^[\$€£₹]?\s?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^[\$€£₹]\s?-?\d+(?:\.\d+)?$|^-?\d+(?:\.\d+)?\s?[\$€£₹%]$")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_BOOL = {"true", "false", "yes", "no", "y", "n", "t", "f"}
DATE_PATTERNS = {
    "iso": (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    "slash_ymd": (re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"), "%Y/%m/%d"),
    "slash_dmy_or_mdy": (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"), None),
    "dash_dmy": (re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"), None),
    "d_mon_y": (re.compile(r"^\d{1,2}[ -][A-Za-z]{3}[ -]\d{4}$"), None),
    "mon_d_y": (re.compile(r"^[A-Za-z]{3,9} \d{1,2},? \d{4}$"), None),
}

ALLOWED_OPS = {
    "trim_whitespace", "standardize_nulls", "parse_number", "parse_date", "normalize_case", "map_values",
    "deduplicate", "drop_empty_rows", "flag_invalid_emails", "parse_bool",
}


def read_csv(text: str, max_rows: int = 20_000) -> tuple[list[str], list[list[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader]
    if not rows:
        return [], []
    header = [h.strip() or f"column_{i + 1}" for i, h in enumerate(rows[0])]
    body = []
    for r in rows[1 : max_rows + 1]:
        r = (r + [""] * len(header))[: len(header)]
        body.append(r)
    return header, body


def write_csv(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _is_null(v: str) -> bool:
    return v.strip().lower() in NULL_TOKENS


def _date_kind(v: str) -> str | None:
    for kind, (pattern, _) in DATE_PATTERNS.items():
        if pattern.match(v):
            return kind
    return None


def profile(header: list[str], rows: list[list[str]]) -> dict[str, Any]:
    columns = []
    for ci, name in enumerate(header):
        values = [r[ci] for r in rows]
        non_null = [v for v in values if not _is_null(v)]
        stripped = [v.strip() for v in non_null]
        null_tokens = sorted({v.strip() for v in values if _is_null(v) and v.strip()})
        issues: list[str] = []
        if any(v != v.strip() for v in non_null):
            issues.append("leading_or_trailing_whitespace")
        if null_tokens:
            issues.append("non_standard_null_tokens")
        kind = "empty"
        if stripped:
            n = len(stripped)
            count = lambda pred: sum(1 for v in stripped if pred(v))
            date_kinds = Counter(k for k in (_date_kind(v) for v in stripped) if k)
            if count(lambda v: _INT.match(v)) == n:
                kind = "integer"
            elif count(lambda v: _INT.match(v) or _FLOAT.match(v)) == n:
                kind = "float"
            elif count(lambda v: _INT.match(v) or _FLOAT.match(v) or _FORMATTED_NUM.match(v)) == n:
                kind = "formatted_number"
                issues.append("numbers_with_symbols_or_separators")
            elif sum(date_kinds.values()) >= 0.8 * n:
                kind = "date"
                if len(date_kinds) > 1 or set(date_kinds) - {"iso"}:
                    issues.append("non_iso_or_mixed_date_formats")
            elif count(lambda v: v.lower() in _BOOL) == n:
                kind = "boolean"
                if len({v for v in stripped}) > 2:
                    issues.append("inconsistent_boolean_values")
            elif count(lambda v: "@" in v) >= 0.8 * n:
                kind = "email"
                if count(lambda v: not _EMAIL.match(v)):
                    issues.append("invalid_emails")
            else:
                distinct = set(stripped)
                folded = {v.lower() for v in distinct}
                if len(folded) <= max(20, n // 10) and n >= 2 * len(folded):
                    kind = "categorical"
                    if len({v.lower() for v in distinct}) < len(distinct):
                        issues.append("inconsistent_category_casing")
                else:
                    kind = "text"
        columns.append({
            "name": name,
            "type": kind,
            "null_count": len(values) - len(non_null),
            "null_tokens": null_tokens,
            "distinct": len(set(stripped)),
            "samples": list(dict.fromkeys(stripped))[:6],
            "issues": issues,
            "dayfirst": _infer_dayfirst(stripped) if kind == "date" else None,
        })
    dupes = len(rows) - len({tuple(r) for r in rows})
    empty = sum(1 for r in rows if all(_is_null(v) for v in r))
    return {"row_count": len(rows), "column_count": len(header), "duplicate_rows": dupes, "empty_rows": empty, "columns": columns}


def _infer_dayfirst(values: list[str]) -> bool | None:
    firsts, seconds = [], []
    for v in values:
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-]\d{4}$", v)
        if m:
            firsts.append(int(m.group(1)))
            seconds.append(int(m.group(2)))
    if not firsts:
        return None
    if any(f > 12 for f in firsts):
        return True
    if any(s > 12 for s in seconds):
        return False
    return None  # ambiguous: every value fits both D/M and M/D


def _parse_date(v: str, dayfirst: bool) -> str | None:
    v = v.strip()
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y", "%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y"]
    formats += ["%d/%m/%Y", "%d-%m-%Y"] if dayfirst else ["%m/%d/%Y", "%m-%d-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def apply_plan(header: list[str], rows: list[list[str]], plan: list[dict]) -> tuple[list[str], list[list[str]], list[dict]]:
    """Apply validated operations in order. Returns new header, rows and a per-operation change log."""
    rows = [list(r) for r in rows]
    header = list(header)
    log = []
    for step in plan:
        op, col, params = step["op"], step.get("column"), step.get("params") or {}
        idx = header.index(col) if col else None
        targets = [idx] if idx is not None else list(range(len(header)))
        changed = 0
        unparsed = 0
        if op == "trim_whitespace":
            for r in rows:
                for i in targets:
                    if r[i] != r[i].strip():
                        r[i] = r[i].strip()
                        changed += 1
        elif op == "standardize_nulls":
            for r in rows:
                for i in targets:
                    if _is_null(r[i]) and r[i] != "":
                        r[i] = ""
                        changed += 1
        elif op == "parse_number":
            for r in rows:
                v = r[idx]
                if _is_null(v):
                    continue
                clean = re.sub(r"[\s,\$€£₹%]", "", v)
                try:
                    num = float(clean)
                    new = str(int(num)) if num.is_integer() else f"{num:.10g}"
                    if new != v:
                        r[idx] = new
                        changed += 1
                except ValueError:
                    unparsed += 1
        elif op == "parse_date":
            dayfirst = bool(params.get("dayfirst", False))
            for r in rows:
                if _is_null(r[idx]):
                    continue
                new = _parse_date(r[idx], dayfirst)
                if new is None:
                    unparsed += 1
                elif new != r[idx]:
                    r[idx] = new
                    changed += 1
        elif op == "normalize_case":
            fn = {"lower": str.lower, "upper": str.upper, "title": str.title}[params.get("mode", "lower")]
            for r in rows:
                if r[idx] and fn(r[idx]) != r[idx]:
                    r[idx] = fn(r[idx])
                    changed += 1
        elif op == "map_values":
            mapping = {str(k): str(v) for k, v in (params.get("mapping") or {}).items()}
            for r in rows:
                if r[idx] in mapping and mapping[r[idx]] != r[idx]:
                    r[idx] = mapping[r[idx]]
                    changed += 1
        elif op == "parse_bool":
            truthy = {"true", "yes", "y", "t", "1"}
            for r in rows:
                v = r[idx].strip().lower()
                if not v:
                    continue
                new = "true" if v in truthy else "false" if v in {"false", "no", "n", "f", "0"} else None
                if new is None:
                    unparsed += 1
                elif new != r[idx]:
                    r[idx] = new
                    changed += 1
        elif op == "flag_invalid_emails":
            header.append(f"{col}_is_valid")
            for r in rows:
                ok = bool(_EMAIL.match(r[idx].strip())) if r[idx].strip() else False
                r.append("true" if ok else "false")
                changed += 0 if ok else 1
        elif op == "drop_empty_rows":
            before = len(rows)
            rows = [r for r in rows if not all(_is_null(v) for v in r)]
            changed = before - len(rows)
        elif op == "deduplicate":
            keys = [header.index(c) for c in params.get("columns", [])] or list(range(len(header)))
            seen, kept = set(), []
            for r in rows:
                k = tuple(r[i].strip().lower() for i in keys)
                if k in seen:
                    changed += 1
                    continue
                seen.add(k)
                kept.append(r)
            rows = kept
        log.append({"op": op, "column": col, "changed": changed, "unparsed": unparsed})
    return header, rows, log


def validate_plan(plan: list[dict], header: list[str]) -> tuple[list[dict], list[dict]]:
    """Keep only allowlisted operations on existing columns. Returns (valid, rejected)."""
    needs_column = {"parse_number", "parse_date", "normalize_case", "map_values", "flag_invalid_emails", "parse_bool"}
    valid, rejected = [], []
    for step in plan:
        op, col = step.get("op"), step.get("column")
        if op not in ALLOWED_OPS:
            rejected.append({**step, "reason": "operation not allowlisted"})
        elif col is not None and col not in header:
            rejected.append({**step, "reason": f"unknown column {col!r}"})
        elif op in needs_column and col is None:
            rejected.append({**step, "reason": "column required"})
        elif op == "normalize_case" and (step.get("params") or {}).get("mode", "lower") not in ("lower", "upper", "title"):
            rejected.append({**step, "reason": "invalid case mode"})
        else:
            valid.append(step)
    return valid, rejected
