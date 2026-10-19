"""Log parsing, templating, clustering and spike detection. All deterministic."""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

LEVELS = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "WARNING": 3, "ERROR": 4, "FATAL": 5, "CRITICAL": 5}
CANON = {"WARNING": "WARN", "CRITICAL": "FATAL"}

_TEXT_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"\[?(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\]?\s+"
    r"(?:\[(?P<svc>[^\]]+)\]\s+)?(?P<msg>.*)$",
    re.IGNORECASE,
)
_CONTINUATION = re.compile(r"^(\s+|Traceback \(most recent call last\)|Caused by:|\s*at )")
_VARIABLE_PARTS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE), "<uuid>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b((?:request|req|trace|span|user|order|session|txn)_?id)=[^\s,)]+", re.IGNORECASE), r"\1=<id>"),
    (re.compile(r"\b(?=[a-z_-]*\d)(?=\d*[a-z])[a-z0-9_-]{8,}\b", re.IGNORECASE), "<id>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (re.compile(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{12,}\b", re.IGNORECASE), "<hex>"),
    (re.compile(r"(?<=[=:])\s*\"[^\"]*\"|'[^']*'"), "<str>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|MB|KB|GB|%)?\b"), "<num>"),
]
DEPLOY = re.compile(r"\b(deploy(?:ed|ment)?|release[d]?|rollout|rolled out|starting version|new version)\b", re.IGNORECASE)


@dataclass
class LogEvent:
    ts: datetime | None
    level: str
    service: str
    message: str
    extra: list[str] = field(default_factory=list)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.replace(",", ".").replace(" ", "T", 1)
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo is None else dt.astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def parse_logs(text: str, max_lines: int = 50_000) -> list[LogEvent]:
    events: list[LogEvent] = []
    for raw in text.splitlines()[:max_lines]:
        line = raw.rstrip()
        if not line:
            continue
        if line.lstrip().startswith("{"):
            try:
                obj = json.loads(line)
                level = str(obj.get("level") or obj.get("severity") or "INFO").upper()
                events.append(LogEvent(
                    ts=_parse_ts(str(obj.get("ts") or obj.get("timestamp") or obj.get("time") or "")),
                    level=CANON.get(level, level if level in LEVELS else "INFO"),
                    service=str(obj.get("service") or obj.get("svc") or "unknown"),
                    message=str(obj.get("msg") or obj.get("message") or ""),
                ))
                continue
            except json.JSONDecodeError:
                pass
        if events and _CONTINUATION.match(line):
            events[-1].extra.append(line.strip())
            continue
        m = _TEXT_LINE.match(line)
        if m:
            level = m.group("level").upper()
            events.append(LogEvent(_parse_ts(m.group("ts")), CANON.get(level, level), m.group("svc") or "unknown",
                                   m.group("msg")))
        else:
            upper = line.upper()
            level = next((lv for lv in ("FATAL", "ERROR", "WARN", "INFO", "DEBUG") if lv in upper), "INFO")
            events.append(LogEvent(None, level, "unknown", line))
    return events


def template(message: str) -> str:
    out = message
    for pattern, token in _VARIABLE_PARTS:
        out = pattern.sub(token, out)
    return re.sub(r"\s+", " ", out).strip()[:240]


def cluster(events: list[LogEvent], min_level: str = "WARN") -> list[dict]:
    threshold = LEVELS[min_level]
    groups: dict[tuple[str, str], list[LogEvent]] = defaultdict(list)
    for e in events:
        if LEVELS.get(e.level, 2) >= threshold:
            groups[(e.level, template(e.message))].append(e)
    clusters = []
    for i, ((level, tpl), evs) in enumerate(sorted(groups.items(), key=lambda kv: (-LEVELS[kv[0][0]], -len(kv[1]), kv[0][1]))):
        stamps = [e.ts for e in evs if e.ts]
        clusters.append({
            "id": f"C{i + 1}",
            "level": level,
            "template": tpl,
            "count": len(evs),
            "services": sorted({e.service for e in evs}),
            "first_seen": min(stamps).isoformat() if stamps else None,
            "last_seen": max(stamps).isoformat() if stamps else None,
            "sample": evs[0].message[:300],
            "stack_hint": evs[0].extra[-1][:200] if evs[0].extra else None,
        })
    return clusters


def error_histogram(events: list[LogEvent]) -> dict[str, int]:
    hist: Counter[str] = Counter()
    for e in events:
        if e.ts and LEVELS.get(e.level, 2) >= LEVELS["ERROR"]:
            hist[e.ts.strftime("%Y-%m-%dT%H:%M")] += 1
    return dict(sorted(hist.items()))


def detect_spikes(hist: dict[str, int], min_count: int = 5) -> list[dict]:
    if len(hist) < 2:
        return []
    values = list(hist.values())
    # Robust statistics: the spike itself must not inflate the threshold (as a stdev would).
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    limit = max(min_count, median + 3 * 1.4826 * mad, 2 * median)
    return [{"minute": k, "errors": v, "threshold": round(limit, 1)} for k, v in hist.items() if v >= limit]


def deploy_markers(events: list[LogEvent]) -> list[dict]:
    return [
        {"ts": e.ts.isoformat() if e.ts else None, "service": e.service, "message": e.message[:200]}
        for e in events if DEPLOY.search(e.message) and LEVELS.get(e.level, 2) <= LEVELS["INFO"]
    ]


def level_counts(events: list[LogEvent]) -> dict[str, int]:
    return dict(Counter(e.level for e in events))
