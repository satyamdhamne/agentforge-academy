"""Offline responder: keyword rules map error clusters to common failure hypotheses."""

from __future__ import annotations

import re

from ..core import CompletionRequest

PATTERNS = [
    (r"too many connections|pool (?:exhausted|timeout)|queuepool limit|overflow \d+ reached|deadlock|lock wait|remaining connection slots",
     "Database connection pool exhaustion or lock contention",
     ["Inspect active connections and long-running queries", "Check pool size vs. replica count",
      "Look for transactions held open across network calls"]),
    (r"timed? ?out|timeout|deadline exceeded|504", "Downstream dependency is slow or timing out",
     ["Check latency dashboards for the dependency named in the errors", "Compare timeout settings with p99 latency",
      "Look for retry storms amplifying load"]),
    (r"connection refused|econnrefused|could not connect|connection reset|unreachable|no route to host",
     "A dependency is unavailable or refusing connections",
     ["Check health/readiness of the target service", "Verify DNS, security groups and service discovery",
      "Check whether the dependency was restarted or scaled to zero"]),
    (r"out of memory|oomkilled|memoryerror|heap|cannot allocate", "Memory exhaustion",
     ["Check container memory metrics and OOM kill events", "Profile allocations around the failing code path",
      "Compare memory limits before and after the latest deploy"]),
    (r"\b(401|403)\b|unauthori[sz]ed|forbidden|token (?:expired|invalid)|signature", "Authentication or credential failure",
     ["Check credential/secret rotation events", "Verify token expiry and clock skew", "Confirm IAM/role changes"]),
    (r"no space left|disk full|enospc", "Disk is full",
     ["Check volume usage", "Identify large log/temp files", "Add retention or expand the volume"]),
    (r"nullpointer|typeerror|keyerror|attributeerror|undefined is not|cannot read propert|indexerror|valueerror",
     "Application bug in a recent code path",
     ["Inspect the stack trace and the latest diff touching it", "Reproduce with the failing input",
      "Consider rolling back the latest deploy"]),
    (r"\b5\d\d\b|internal server error|bad gateway|service unavailable", "Upstream service returning 5xx errors",
     ["Identify which upstream returns 5xx", "Check its error logs and recent deploys"]),
]


def hypothesize(request: CompletionRequest) -> dict:
    clusters = request.context.get("clusters", [])
    spikes = request.context.get("spikes", [])
    correlations = {c["cluster"]: c for c in request.context.get("correlations", [])}
    levels = request.context.get("levels", {})
    found: dict[str, dict] = {}
    for c in clusters:
        text = f"{c['template']} {c.get('sample', '')} {c.get('stack_hint') or ''}".lower()
        for pattern, title, steps in PATTERNS:
            if re.search(pattern, text):
                h = found.setdefault(title, {"title": title, "evidence": [], "next_steps": steps, "weight": 0})
                h["evidence"].append(c["id"])
                h["weight"] += c["count"] * (2 if c["level"] in ("ERROR", "FATAL") else 1)
                if c["id"] in correlations:
                    h["weight"] *= 2
                    h["explanation"] = (f"Cluster {c['id']} first appeared {correlations[c['id']]['minutes_after']} min "
                                        f"after a deploy marker.")
                break
    ranked = sorted(found.values(), key=lambda h: -h["weight"])[:4]
    hypotheses = []
    for h in ranked:
        confidence = "high" if h["weight"] >= 20 else "medium" if h["weight"] >= 5 else "low"
        hypotheses.append({"title": h["title"], "confidence": confidence, "evidence": h["evidence"],
                           "explanation": h.get("explanation", f"Supported by {len(h['evidence'])} error cluster(s)."),
                           "next_steps": h["next_steps"]})
    errors = levels.get("ERROR", 0) + levels.get("FATAL", 0)
    severity = "sev1" if levels.get("FATAL", 0) or errors >= 100 else "sev2" if errors >= 20 or spikes else "sev3" if errors else "sev4"
    top = clusters[0]
    summary = (f"{errors} error-level events across {len(clusters)} clusters. Most frequent: '{top['template'][:90]}' "
               f"({top['count']}x).")
    if spikes:
        summary += f" Error spike at {spikes[0]['minute']} ({spikes[0]['errors']} errors/min)."
    if not hypotheses:
        hypotheses.append({"title": "Unrecognised failure pattern", "confidence": "low", "evidence": [top["id"]],
                           "explanation": "No known pattern matched; inspect the top cluster manually.",
                           "next_steps": ["Read the sample message and stack trace for the top cluster"]})
    return {"summary": summary, "severity": severity, "hypotheses": hypotheses}


RESPONDERS = {"log_analysis.hypothesize": hypothesize}
