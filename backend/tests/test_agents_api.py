from __future__ import annotations


def test_catalog_has_100_agents_with_10_implementations(api):
    d = api.get("/agents").json()
    assert d["total"] == 100
    assert len(d["facets"]["categories"]) == 12
    assert set(d["facets"]["verdicts"]) == {"agent", "workflow", "rag", "deterministic"}
    impl = api.get("/agents", params={"implemented": "true"}).json()
    assert impl["total"] == 10
    assert api.get("/agents", params={"q": "sql"}).json()["total"] >= 2


def test_implemented_agent_detail_has_full_blueprint(api):
    d = api.get("/agents/github-pr-review-agent").json()
    bp = d["blueprint"]
    for key in ("problem", "business_value", "verdict_reasoning", "architecture_mermaid", "data_flow", "framework", "model_selection",
                "prompts", "tools", "state_memory", "folder_structure", "env_vars", "install", "run_local", "tests", "evaluation",
                "security", "cost_latency", "deployment", "observability", "failure_modes", "improvements", "production_checklist",
                "challenges", "interview_questions"):
        assert bp.get(key), key
    assert d["runnable"] and d["examples"] and d["example_runs"]
    assert d["eval_report"]["pass_rate"] == 1.0
    assert any(f.endswith("pr_review/agent.py") for f in d["files"])
    f = api.get(f"/agents/github-pr-review-agent/files/{d['files'][0]}").json()
    assert f["content"]


def test_blueprint_agent_is_not_runnable(learner):
    d = learner.get("/agents/code-explanation-agent").json()
    assert d["runnable"] is False and d["blueprint"]["verdict_reasoning"]
    r = learner.post("/agents/code-explanation-agent/runs", {"example_index": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_runnable"


def test_run_agent_with_mock_provider(learner):
    r = learner.post("/agents/sql-query-assistant/runs", {"example_index": 0})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "succeeded" and run["is_mock"] is True and run["cost_usd"] == 0
    assert run["trace"] and run["trace_id"] and run["output"]["sql"]
    assert learner.get(f"/agents/runs/{run['id']}").json()["id"] == run["id"]
    assert learner.get("/agents/runs/mine").json()["items"][0]["id"] == run["id"]


def test_invalid_input_fails_cleanly(learner):
    r = learner.post("/agents/sql-query-assistant/runs", {"input": {"nonsense": True}}).json()
    assert r["status"] == "failed" and "Invalid input" in r["error"]


def test_side_effects_require_approval(learner, app):
    from tests.conftest import Api

    run = learner.post("/agents/bug-triage-agent/runs", {"example_index": 0}).json()
    assert run["status"] == "awaiting_approval" and run["pending_actions"]

    stranger = Api(app)
    stranger.register()
    assert stranger.post(f"/agents/runs/{run['id']}/decision", {"decision": "approve"}).status_code == 404
    approved = learner.post(f"/agents/runs/{run['id']}/decision", {"decision": "approve", "note": "LGTM"}).json()
    assert approved["status"] == "approved" and approved["approval_result"]["decision"] == "approve"
    again = learner.post(f"/agents/runs/{run['id']}/decision", {"decision": "reject"})
    assert again.status_code == 409


def test_other_users_cannot_read_runs(learner, app):
    from tests.conftest import Api

    run = learner.post("/agents/log-analysis-agent/runs", {"example_index": 0}).json()
    other = Api(app)
    other.register()
    assert other.get(f"/agents/runs/{run['id']}").status_code == 404


def test_daily_quota_enforced(learner):
    from app.core.db import SessionLocal
    from app.models import Entitlement

    with SessionLocal() as db:
        ent = db.query(Entitlement).filter_by(plan="free", feature_key="agent_runs_per_day").one()
        old, ent.limit_value = ent.limit_value, 1
        db.commit()
    try:
        assert learner.post("/agents/csv-cleaning-agent/runs", {"example_index": 0}).status_code == 201
        r = learner.post("/agents/csv-cleaning-agent/runs", {"example_index": 0})
        assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"
    finally:
        with SessionLocal() as db:
            db.query(Entitlement).filter_by(plan="free", feature_key="agent_runs_per_day").one().limit_value = old
            db.commit()


def test_runs_require_auth(api):
    assert api.post("/agents/sql-query-assistant/runs", {"example_index": 0}).status_code == 401
