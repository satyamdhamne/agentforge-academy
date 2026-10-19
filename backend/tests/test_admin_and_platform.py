from __future__ import annotations


def _lesson_id(admin, slug):
    items = admin.get("/admin/lessons", params={"page_size": 200}).json()["items"]
    return next(i["id"] for i in items if i["slug"] == slug)


def test_cms_requires_roles(learner, api):
    assert api.get("/admin/lessons").status_code == 401
    assert learner.get("/admin/lessons").status_code == 403
    assert learner.get("/admin/analytics").status_code == 403


def test_versioned_publishing_with_four_eyes(author, admin, api):
    lesson_id = _lesson_id(author, "python-generators")
    detail = author.get(f"/admin/lessons/{lesson_id}").json()
    content = detail["latest_content"]

    incomplete = author.post(f"/admin/lessons/{lesson_id}/versions", {"content": {"sections": {}}, "change_note": "oops"})
    assert incomplete.status_code == 422 and "explanation" in incomplete.json()["error"]["details"]

    content["sections"]["explanation"] += "\n\nEdited by the author."
    v = author.post(f"/admin/lessons/{lesson_id}/versions", {"content": content, "change_note": "Clarify explanation"}).json()
    assert v["status"] == "draft" and v["version"] >= 2
    assert author.post(f"/admin/lesson-versions/{v['id']}/publish").status_code == 403  # authors can't publish
    assert author.post(f"/admin/lesson-versions/{v['id']}/submit").json()["status"] == "review"
    published = admin.post(f"/admin/lesson-versions/{v['id']}/publish").json()
    assert published["status"] == "published"
    live = api.get("/lessons/python-generators").json()
    assert live["version"] == v["version"] and "Edited by the author." in live["content"]["sections"]["explanation"]
    history = admin.get(f"/admin/lessons/{lesson_id}").json()["versions"]
    assert [h["status"] for h in history][:2] == ["published", "archived"]
    logs = admin.get("/admin/audit-logs", params={"entity_type": "lesson"}).json()["items"]
    assert any(x["action"] == "lesson_version.publish" for x in logs)


def test_analytics_and_users(admin, learner):
    learner.post("/agents/sql-query-assistant/runs", {"example_index": 0})
    a = admin.get("/admin/analytics").json()
    k = a["kpis"]
    for key in ("users_total", "activation_rate", "weekly_active_learners", "lesson_completions_7d", "challenge_completions_7d",
                "agent_runs_7d", "paid_conversion", "inference_cost_usd_30d"):
        assert key in k
    assert k["agent_runs_7d"] >= 1 and len(a["series"]) == 14
    users = admin.get("/admin/users").json()
    assert users["total"] >= 3


def test_announcements(author, api):
    r = author.post("/admin/announcements", {"title": "New RAG lab", "body_md": "Try it now.", "publish": True})
    assert r.status_code == 201
    assert api.get("/announcements").json()["items"][0]["title"] == "New RAG lab"


def test_health_and_openapi(app):
    from fastapi.testclient import TestClient

    c = TestClient(app)
    assert c.get("/healthz").json() == {"status": "ok"}
    ready = c.get("/readyz").json()
    assert ready["status"] == "ready" and ready["llm_provider"] == "mock"
    spec = c.get("/api/v1/openapi.json").json()
    assert "/api/v1/challenges/{slug}/attempts" in spec["paths"]


def test_security_headers_and_error_envelope(api):
    r = api.get("/tracks/nope")
    body = r.json()["error"]
    assert body["code"] == "not_found" and body["trace_id"] == r.headers["x-trace-id"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    v = api.post("/auth/login", {"email": "not-an-email"})
    assert v.status_code == 422 and v.json()["error"]["code"] == "validation_error"


def test_sandbox_status_and_run(learner, sandbox):
    st = learner.get("/sandbox/status").json()
    assert st["available"] is True
    r = learner.post("/sandbox/run", {"language": "python", "code": "print(sum(range(5)))"}).json()
    assert r["status"] == "ok" and r["stdout"].strip() == "10"
    js = learner.post("/sandbox/run", {"language": "javascript", "code": "console.log([1,2].map(x => x * 2))"}).json()
    assert js["stdout"].strip() == "[2,4]"
    loop = learner.post("/sandbox/run", {"language": "python", "code": "while True: pass"}).json()
    assert loop["timed_out"] is True


def test_sandbox_disabled_is_explicit(learner):
    st = learner.get("/sandbox/status").json()
    assert st["available"] is False and st["mode"] == "disabled"
    r = learner.post("/sandbox/run", {"language": "python", "code": "print(1)"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "sandbox_disabled"


def test_seed_is_idempotent():
    from app.core.db import SessionLocal
    from app.seed.loader import seed_all

    with SessionLocal() as db:
        out = seed_all(db, with_users=True, with_agent_runs=False)
    assert out["agents"]["versions_created"] == 0 and out["users_created"] == []
