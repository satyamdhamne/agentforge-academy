"""Offline responder for `pr_review.review`.

It turns rule-engine findings into a review deterministically. It is labelled as mock output
everywhere in the product; it demonstrates the pipeline, not model judgement.
"""

from __future__ import annotations

from collections import Counter

from ..core import CompletionRequest


def review(request: CompletionRequest) -> dict:
    findings = request.context.get("findings", [])
    stats = request.context.get("stats", {})
    sev = Counter(f["severity"] for f in findings)
    comments = [
        {"file": f["file"], "line": f["line"], "severity": f["severity"], "message": f["message"],
         "suggestion": f["suggestion"], "rule": f["rule"]}
        for f in findings if f["severity"] != "info"
    ][:10]
    if sev["high"]:
        verdict = "request_changes"
    elif sev["medium"]:
        verdict = "comment"
    else:
        verdict = "approve"
    parts = [f"Reviewed {stats.get('files_changed', 0)} file(s), +{stats.get('additions', 0)}/-{stats.get('deletions', 0)}."]
    if findings:
        parts.append("Findings: " + ", ".join(f"{n} {s}" for s, n in sev.items()) + ".")
        top = next((f for f in findings if f["severity"] == "high"), None)
        if top:
            parts.append(f"Most important: {top['message'].rstrip('.')} in {top['file']}.")
    else:
        parts.append("No issues detected by the rule engine.")
    praise = []
    if stats.get("test_files_changed"):
        praise.append("Tests were updated alongside the change.")
    if not sev["high"] and 0 < stats.get("additions", 0) < 150:
        praise.append("Small, focused change that is easy to review.")
    return {"summary": " ".join(parts), "verdict": verdict, "comments": comments, "praise": praise}


RESPONDERS = {"pr_review.review": review}
