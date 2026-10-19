from __future__ import annotations

from app.modules.admin import REQUIRED_SECTIONS


def test_catalog_lists_16_tracks_with_counts(api):
    items = api.get("/tracks").json()["items"]
    assert len(items) == 16
    by_slug = {t["slug"]: t for t in items}
    assert by_slug["javascript-typescript"]["lessons_available"] >= 2
    assert all(t["lessons_total"] >= t["lessons_available"] for t in items)


def test_track_detail_marks_coming_soon_and_locked(api):
    t = api.get("/tracks/aws-devops").json()
    lessons = [lesson for c in t["courses_detail"] for m in c["modules"] for lesson in m["lessons"]]
    iam = next(x for x in lessons if x["slug"] == "iam-least-privilege")
    assert iam["tier"] == "pro" and iam["locked"] is True
    assert any(not x["available"] for x in lessons)
    assert api.get("/tracks/does-not-exist").status_code == 404


def test_lesson_has_every_required_section_and_hides_quiz_answers(api):
    d = api.get("/lessons/js-closures").json()
    assert d["locked"] is False
    for s in REQUIRED_SECTIONS:
        assert d["content"]["sections"].get(s), s
    assert d["quiz"] and all("answer" not in q for q in d["quiz"])
    assert d["exercises"][0]["slug"] == "js-once"
    assert d["breadcrumb"]["track"]["slug"] == "javascript-typescript"


def test_unpublished_lesson_is_404(api):
    assert api.get("/lessons/dns-explained").status_code == 404


def test_completion_requires_quiz_then_awards_badge(learner):
    lesson = learner.get("/lessons/js-closures").json()
    r = learner.post("/lessons/js-closures/progress", {"status": "completed"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "quiz_required"

    wrong = {q["id"]: 0 for q in lesson["quiz"]}
    r = learner.post("/lessons/js-closures/quiz", {"answers": wrong}).json()
    assert r["passed"] is False and all("explanation" in x for x in r["results"])
    right = {x["id"]: x["correct_index"] for x in r["results"]}
    assert learner.post("/lessons/js-closures/quiz", {"answers": right}).json()["score"] == 1.0

    r = learner.post("/lessons/js-closures/progress", {"status": "completed"}).json()
    assert r["status"] == "completed"
    assert "first-lesson" in [a["slug"] for a in r["new_achievements"]]
    again = learner.post("/lessons/js-closures/progress", {"status": "completed"}).json()
    assert again["new_achievements"] == []  # badges are granted once


def test_dashboard_and_progress(learner):
    assert learner.post("/tracks/rag-engineering/enroll").status_code == 201
    d = learner.get("/me/dashboard").json()
    assert d["stats"]["lessons_completed"] == 0
    assert [t["slug"] for t in d["enrolled_tracks"]] == ["rag-engineering"]
    assert d["continue_lesson"]["slug"]
    assert d["daily_challenge"]["slug"]
    assert len(d["activity"]) == 7 and d["plan"] == "free"
    p = learner.get("/me/progress").json()
    assert p["tracks"][0]["slug"] == "rag-engineering"


def test_dashboard_requires_auth(api):
    r = api.get("/me/dashboard")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert r.headers.get("x-trace-id")


def test_pro_content_locked_for_free_unlocked_for_paid(learner, admin):
    from app.core.db import SessionLocal
    from app.models import Lesson

    with SessionLocal() as db:  # temporarily mark a published lesson as pro
        lesson = db.query(Lesson).filter_by(slug="python-generators").one()
        lesson.tier = "pro"
        db.commit()
    try:
        assert learner.get("/lessons/python-generators").json()["locked"] is True
        assert learner.post("/lessons/python-generators/progress", {"status": "in_progress"}).status_code == 402
        r = admin.patch(f"/admin/users/{learner.user['id']}/plan", {"plan": "pro"})
        assert r.status_code == 200
        assert learner.get("/lessons/python-generators").json()["locked"] is False
    finally:
        with SessionLocal() as db:
            db.query(Lesson).filter_by(slug="python-generators").one().tier = "free"
            db.commit()


def test_plans_projects_achievements_public(api):
    plans = api.get("/plans").json()
    assert [p["key"] for p in plans["items"]] == ["free", "pro", "team"] and plans["payments_enabled"] is False
    assert len(api.get("/projects").json()["items"]) >= 5
    assert len(api.get("/achievements").json()["items"]) >= 8
    assert api.get("/announcements").json()["items"]
