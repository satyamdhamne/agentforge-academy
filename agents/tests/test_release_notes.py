from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.release_notes import EXAMPLE_COMMITS, SPEC
from agentforge_agents.release_notes.agent import parse_commits


def test_parse_conventional_commits():
    c = {x["hash"]: x for x in parse_commits(EXAMPLE_COMMITS)}
    assert c["d4e5f6a"]["section"] == "breaking"
    assert c["e5f6a7b"]["section"] == "security"
    assert c["a1b2c3d"]["prs"] == ["412"] and c["a1b2c3d"]["scope"] == "search"
    assert c["f6a7b8c"]["section"] == "other"


def test_invented_items_are_dropped_and_missing_items_fall_back():
    def responder(req):
        first = req.context["items"][0]["id"]
        return {"highlights": [], "items": [{"id": first, "text": "Nice."}, {"id": 999, "text": "Free unicorns for everyone."}]}

    out = run_agent(SPEC, {"commits": EXAMPLE_COMMITS, "version": "1.0.0", "audience": "customers", "release_date": "2026-01-01"},
                    provider=MockProvider({"release_notes.rewrite": responder})).output
    assert out["dropped_items"][0]["id"] == 999
    assert "unicorns" not in out["markdown"]
    assert len(out["fallback_items"]) == 4


def test_developer_notes_never_call_a_model():
    r = run_agent(SPEC, {"commits": "feat: x", "version": "1.0.0", "release_date": "2026-01-01"})
    assert r.llm_calls == 0
