from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.log_analysis import SPEC, _example_logs
from agentforge_agents.log_analysis.tools import cluster, detect_spikes, parse_logs, template


def test_template_normalises_variable_parts():
    a = template("timeout after 3000ms for user 42 from 10.0.0.1 (request_id=abc123def)")
    b = template("timeout after 15ms for user 7 from 10.2.3.4 (request_id=zz9999zzz)")
    assert a == b


def test_parse_mixed_formats_and_stack_continuations():
    text = ('{"ts": "2026-01-01T00:00:00Z", "level": "error", "msg": "boom"}\n'
            "2026-01-01T00:01:00Z ERROR [api] KeyError: 'x'\n"
            "Traceback (most recent call last):\n  File \"a.py\", line 1, in f\n")
    events = parse_logs(text)
    assert [e.level for e in events] == ["ERROR", "ERROR"]
    assert events[1].service == "api" and len(events[1].extra) == 2


def test_spike_detection_is_robust_to_the_spike_itself():
    hist = {"10:00": 2, "10:01": 3, "10:02": 2, "10:03": 25, "10:04": 3}
    spikes = detect_spikes(hist)
    assert [s["minute"] for s in spikes] == ["10:03"]


def test_clusters_sorted_by_severity_then_count():
    events = parse_logs("2026-01-01T00:00:00Z WARN [a] slow 1\n" * 5 + "2026-01-01T00:00:00Z ERROR [a] fail\n")
    c = cluster(events)
    assert c[0]["level"] == "ERROR" and c[1]["count"] == 5


def test_hypothesis_evidence_must_reference_real_clusters():
    bad = {"summary": "x", "severity": "sev3", "hypotheses": [
        {"title": "Made up", "confidence": "high", "evidence": ["C99"], "next_steps": []}]}
    out = run_agent(SPEC, {"logs": _example_logs()}, provider=MockProvider({"log_analysis.hypothesize": lambda r: bad})).output
    assert out["hypotheses"][0]["evidence"] == []
    assert out["hypotheses"][0]["confidence"] == "medium"
