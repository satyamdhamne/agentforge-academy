"""Offline planner: maps profile issues to operations with fixed rules."""

from __future__ import annotations

from ..core import CompletionRequest


def plan(request: CompletionRequest) -> dict:
    prof = request.context["profile"]
    steps, notes = [], []
    if any("leading_or_trailing_whitespace" in c["issues"] for c in prof["columns"]):
        steps.append({"op": "trim_whitespace", "reason": "Values have surrounding whitespace."})
    if any(c["null_tokens"] for c in prof["columns"]):
        tokens = sorted({t for c in prof["columns"] for t in c["null_tokens"]})
        steps.append({"op": "standardize_nulls", "reason": f"Null markers found: {', '.join(tokens)}."})
    if prof["empty_rows"]:
        steps.append({"op": "drop_empty_rows", "reason": f"{prof['empty_rows']} fully empty row(s)."})
    for c in prof["columns"]:
        name = c["name"]
        if c["type"] == "formatted_number":
            steps.append({"op": "parse_number", "column": name, "reason": "Strip currency symbols and thousands separators."})
        elif c["type"] == "date" and "non_iso_or_mixed_date_formats" in c["issues"]:
            dayfirst = c["dayfirst"]
            if dayfirst is None:
                notes.append(f"'{name}' dates are ambiguous (every value fits D/M and M/D); assumed month-first.")
            steps.append({"op": "parse_date", "column": name, "params": {"dayfirst": bool(dayfirst)},
                          "reason": "Normalise dates to ISO 8601 (YYYY-MM-DD)."})
        elif c["type"] == "boolean" and "inconsistent_boolean_values" in c["issues"]:
            steps.append({"op": "parse_bool", "column": name, "reason": "Unify yes/no/Y/N/true/false."})
        elif c["type"] == "categorical" and "inconsistent_category_casing" in c["issues"]:
            steps.append({"op": "normalize_case", "column": name, "params": {"mode": "title"},
                          "reason": "Consistent title case for categories."})
        elif c["type"] == "email":
            steps.append({"op": "normalize_case", "column": name, "params": {"mode": "lower"}, "reason": "Emails are case-insensitive."})
            if "invalid_emails" in c["issues"]:
                steps.append({"op": "flag_invalid_emails", "column": name, "reason": "Flag rather than delete invalid emails."})
    id_like = [c["name"] for c in prof["columns"] if c["name"].lower() in ("id", "email", "customer_id", "order_id")]
    if prof["duplicate_rows"] or id_like:
        steps.append({"op": "deduplicate", "params": {"columns": id_like[:1]} if id_like else {},
                      "reason": "Remove duplicate records" + (f" by {id_like[0]}." if id_like else ".")})
    return {"steps": steps, "notes": notes}


RESPONDERS = {"csv_cleaning.plan": plan}
