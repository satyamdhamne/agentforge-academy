"""Phase 6: Interview Arena, Portfolio verification and the opt-in AI mentor."""

from __future__ import annotations

GOOD_ANSWER = (
    "The event loop runs one task at a time on the call stack. After each macrotask, such as a timer from setTimeout or an I/O "
    "callback, it drains the whole microtask queue, which holds promise callbacks and await continuations. This is why a resolved "
    "promise's then callback runs before setTimeout(fn, 0): because microtasks always run first. The trade-off is that a long "
    "chain of microtasks can starve rendering, so for heavy work you should yield back with a timer instead. For example, "
    "Promise.resolve().then(log) logs before a zero-delay timeout."
)


def test_tracks_and_question_bank(api):
    d = api.get("/interviews/tracks").json()
    assert len(d["items"]) == 19 and all(t["questions"] >= 4 for t in d["items"])
    assert {r["criterion"] for r in d["rubric"]} == {"technical_accuracy", "reasoning", "tradeoffs", "communication"}
    assert "not a prediction" in d["disclaimer"]
    qs = api.get("/interviews/questions", params={"track": "rag"}).json()["items"]
    q = qs[0]
    for key in ("concise_answer", "explanation", "example", "follow_ups", "common_mistakes", "difficulty", "key_points"):
        assert q[key], key


def test_mock_interview_scores_transparently(learner):
    s = learner.post("/interviews/sessions", {"track": "javascript", "count": 4}).json()
    assert s["scorer"] == "rubric" and all("concise_answer" not in q for q in s["questions"])
    loop_q = next(q for q in s["questions"] if "event loop" in q["prompt"])
    good = learner.post(f"/interviews/sessions/{s['id']}/answers", {"question_id": loop_q["id"], "answer_text": GOOD_ANSWER}).json()
    assert good["scores"]["technical_accuracy"] >= 0.8 and good["scores"]["tradeoffs"] > 0 and good["overall"] >= 0.7
    assert "Covered" in good["feedback"]["technical_accuracy"] and good["question"]["concise_answer"]
    other = next(q for q in s["questions"] if q["id"] != loop_q["id"])
    weak = learner.post(f"/interviews/sessions/{s['id']}/answers", {"question_id": other["id"], "answer_text": "Not sure."}).json()
    assert weak["overall"] < 0.3 and "Missing" in weak["feedback"]["technical_accuracy"]
    dup = learner.post(f"/interviews/sessions/{s['id']}/answers", {"question_id": other["id"], "answer_text": "again"})
    assert dup.status_code == 409
    done = learner.post(f"/interviews/sessions/{s['id']}/finish").json()
    assert done["status"] == "completed" and done["summary"]["answered"] == 2 and done["summary"]["focus_next"]
    assert learner.post(f"/interviews/sessions/{s['id']}/answers", {"question_id": s["questions"][2]["id"], "answer_text": "x"}).status_code == 409
    assert learner.get("/interviews/sessions").json()["items"][0]["id"] == s["id"]


def test_portfolio_publish_and_verification(learner, admin, api):
    p = learner.get("/me/portfolio").json()
    assert p["is_public"] is False
    bad = learner.post("/me/portfolio/entries", {"title": "Shortener", "repo_url": "http://insecure.example.com"})
    assert bad.status_code == 422
    e = learner.post("/me/portfolio/entries", {
        "title": "URL shortener", "project_slug": "url-shortener-api", "repo_url": "https://github.com/example/shortener",
        "skills": ["FastAPI", "PostgreSQL"], "architecture_mermaid": "flowchart LR\n A[Client] --> B[API] --> C[(Postgres)]",
        "notes_md": "Built a FastAPI service with collision-safe codes, SSRF protection on target URLs, per-IP rate limits, Alembic migrations and a Docker Compose setup that starts from a clean clone.",
        "tests_md": "pytest suite with 41 tests, 88% coverage; load-tested 500 rps with k6."}).json()
    assert e["review_status"] == "draft" and e["project"]["slug"] == "url-shortener-api"
    assert api.get(f"/portfolios/{p['slug']}").status_code == 404  # private until published
    learner.patch("/me/portfolio", {"headline": "Backend engineer learning AI systems", "is_public": True})
    pub = api.get(f"/portfolios/{p['slug']}").json()
    assert pub["entries"] == []  # drafts aren't shown publicly

    submitted = learner.post(f"/me/portfolio/entries/{e['id']}/submit").json()
    assert submitted["review_status"] == "submitted"
    queue = admin.get("/admin/portfolio-reviews").json()["items"]
    assert any(i["id"] == e["id"] for i in queue)
    assert learner.get("/admin/portfolio-reviews").status_code == 403
    r = admin.post(f"/admin/portfolio-entries/{e['id']}/review", {"decision": "verify", "feedback": "Solid tests and clear notes."}).json()
    assert r["review_status"] == "verified" and "verified-project" in r["new_achievements"]
    pub = api.get(f"/portfolios/{p['slug']}").json()
    assert pub["entries"][0]["verified"] is True and any(b["name"] == "Shipped It" for b in pub["badges"])
    edited = learner.put(f"/me/portfolio/entries/{e['id']}", {"title": "URL shortener v2", "repo_url": "https://github.com/example/shortener"}).json()
    assert edited["review_status"] == "draft" and edited["verified"] is False  # edits need re-verification


def test_submit_requires_evidence(learner):
    e = learner.post("/me/portfolio/entries", {"title": "Thin entry"}).json()
    r = learner.post(f"/me/portfolio/entries/{e['id']}/submit")
    assert r.status_code == 422 and r.json()["error"]["code"] == "repo_required"


def test_mentor_is_opt_in_and_grounded(learner):
    r = learner.post("/mentor/ask", {"message": "What is a closure?"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "mentor_opt_in_required"
    learner.patch("/me/profile", {"mentor_opt_in": True})
    a = learner.post("/mentor/ask", {"message": "What is a closure in JavaScript?", "lesson_slug": "js-closures"}).json()
    assert a["citations"] and a["citations"][0]["slug"] == "js-closures" and "[1]" in a["reply"]
    assert a["reply"].strip().endswith("?") and a["stored"] is True
    err = learner.post("/mentor/ask", {"message": "Why does this fail?", "error": "NameError: name 'totl' is not defined"}).json()
    assert "totl" in err["error_help"]
    assert len(learner.get("/mentor/history").json()["items"]) == 4
    assert learner.delete("/mentor/history").status_code == 204
    assert learner.get("/mentor/history").json()["items"] == []


def test_mentor_withholds_solutions_until_attempted_and_asked(learner):
    learner.patch("/me/profile", {"mentor_opt_in": True})
    ask = {"message": "Just give me the full solution", "challenge_slug": "py-two-sum"}
    a = learner.post("/mentor/ask", ask).json()
    assert a["revealed_solution"] is False and "won't hand over" in a["reply"] and "seen = {}" not in a["reply"]
    b = learner.post("/mentor/ask", {**ask, "reveal_solution": True}).json()
    assert b["revealed_solution"] is False  # no attempt yet
    learner.post("/challenges/py-two-sum/attempts", {"code": "def two_sum(nums, target):\n    return []\n"})
    c = learner.post("/mentor/ask", {**ask, "reveal_solution": True}).json()
    assert c["revealed_solution"] is True and "seen" in c["reply"]


def test_assessment_and_adaptive_recommendations(learner):
    qs = learner.get("/mentor/assessment").json()["questions"]
    assert len(qs) == 16
    answers = {q["id"]: (1 if q["area"] in ("programming", "javascript") else 2) for q in qs}
    r = learner.post("/mentor/assessment", {"answers": answers}).json()
    assert r["recommendations"]["start_track"] and r["recommendations"]["gaps"]
    assert learner.get("/mentor/status").json()["assessment"]["recommendations"]["start_track"] == r["recommendations"]["start_track"]
    rec = learner.get("/mentor/recommendations").json()
    assert rec["target_difficulty"] == "beginner" and rec["challenges"]
