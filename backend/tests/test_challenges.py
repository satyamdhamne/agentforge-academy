from __future__ import annotations

TWO_SUM = """
def two_sum(nums, target):
    seen = {}
    for j, x in enumerate(nums):
        if target - x in seen:
            return [seen[target - x], j]
        seen[x] = j
"""


def test_listing_and_filters(api):
    d = api.get("/challenges").json()
    assert d["total"] >= 20
    assert {"coding", "debugging", "rag", "agent", "security", "cloud", "architecture", "prompt", "interview"} <= set(d["categories"])
    rag = api.get("/challenges", params={"category": "rag"}).json()["items"]
    assert rag and all(c["category"] == "rag" for c in rag)
    weekly = api.get("/challenges", params={"weekly": "true"}).json()["items"]
    assert [c["slug"] for c in weekly] == ["weekly-deploy-fastapi-ecs"]


def test_detail_never_leaks_answers(api):
    d = api.get("/challenges/py-two-sum").json()
    assert "solution" not in d and "explanation_md" not in d and "spec" not in d
    assert d["hidden_tests"] == 1 and len(d["public_tests"]) == 3
    mcq = api.get("/challenges/prompt-json-reliability").json()
    assert len(mcq["options"]) == 4 and "correct_index" not in mcq


def test_code_challenge_graded_in_sandbox(learner, sandbox):
    assert learner.get("/challenges/py-two-sum").json()["execution"] == "sandbox"
    bad = learner.post("/challenges/py-two-sum/attempts", {"code": "def two_sum(nums, target):\n    return [0, 1]\n"}).json()
    assert bad["status"] == "failed" and bad["points_awarded"] == 0 and bad["execution_mode"] == "sandbox"
    hidden = [r for r in bad["result"]["results"] if r["hidden"]]
    assert hidden and "expected" not in hidden[0] and "args" not in hidden[0]

    good = learner.post("/challenges/py-two-sum/attempts", {"code": TWO_SUM}).json()
    assert good["status"] == "passed" and good["points_awarded"] == 10
    assert good["solution"] and "first-challenge" in [a["slug"] for a in good["new_achievements"]]

    dup = learner.post("/challenges/py-two-sum/attempts", {"code": TWO_SUM}).json()
    assert dup["duplicate"] is True  # identical resubmission is not re-graded
    again = learner.post("/challenges/py-two-sum/attempts", {"code": TWO_SUM + "\n# tweak"}).json()
    assert again["status"] == "passed" and again["points_awarded"] == 0  # points only once
    assert learner.get("/challenges/py-two-sum").json()["solution"]  # unlocked after solving


def test_sql_challenge(learner, sandbox):
    sql = ("SELECT c.name, COUNT(o.id) AS paid_orders FROM customers c "
           "LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid' GROUP BY c.id, c.name ORDER BY c.name;")
    r = learner.post("/challenges/sql-debug-missing-customers/attempts", {"code": sql}).json()
    assert r["status"] == "passed", r


def test_without_sandbox_code_is_saved_but_not_graded(learner):
    d = learner.get("/challenges/py-two-sum").json()
    assert d["execution"] == "unavailable"
    r = learner.post("/challenges/py-two-sum/attempts", {"code": TWO_SUM}).json()
    assert r["status"] == "not_graded" and r["points_awarded"] == 0 and r["execution_mode"] == "unavailable"


def test_mcq_guessing_earns_less(learner):
    wrong = learner.post("/challenges/cloud-lambda-vs-fargate/attempts", {"selected_index": 0}).json()
    assert wrong["status"] == "failed"
    right = learner.post("/challenges/cloud-lambda-vs-fargate/attempts", {"selected_index": 1}).json()
    assert right["status"] == "passed" and right["points_awarded"] == 5  # 10 points / (1 wrong + 1)


def test_hints_in_order_and_reduce_points(learner):
    assert learner.post("/challenges/arch-cache-strategy/hints/0").json()["points_available"] == 8
    r = learner.post("/challenges/arch-cache-strategy/attempts", {"selected_index": 1}).json()
    assert r["points_awarded"] == 8 and r["hints_used"] == 1
    r = learner.post("/challenges/py-recall-at-k/hints/1")
    assert r.status_code == 400 and r.json()["error"]["code"] == "hint_order"


def test_idempotency_key(learner):
    h = {"Idempotency-Key": "abc-123"}
    first = learner.post("/challenges/security-agent-secrets/attempts", {"selected_index": 2}, headers=h).json()
    second = learner.post("/challenges/security-agent-secrets/attempts", {"selected_index": 0}, headers=h).json()
    assert second["id"] == first["id"] and second["duplicate"] is True


def test_manual_review_flow(learner, admin, author):
    short = learner.post("/challenges/prompt-rewrite-support-bot/attempts", {"answer_text": "too short"})
    assert short.status_code == 422
    essay = " ".join(["Ground every answer in the context and cite the article; escalate when unsure."] * 10)
    r = learner.post("/challenges/prompt-rewrite-support-bot/attempts", {"answer_text": essay}).json()
    assert r["status"] == "pending_review" and r["points_awarded"] == 0
    assert learner.post("/challenges/prompt-rewrite-support-bot/attempts", {"answer_text": essay + " more"}).status_code == 409

    assert author.get("/admin/reviews").status_code == 403  # authors aren't reviewers
    queue = admin.get("/admin/reviews").json()["items"]
    item = next(i for i in queue if i["id"] == r["id"])
    criteria = [c["criterion"] for c in item["exercise"]["rubric"]]
    bad = admin.post(f"/admin/attempts/{r['id']}/review", {"scores": {"grounding": 1}, "feedback": "Partial scores only."})
    assert bad.status_code == 422
    done = admin.post(f"/admin/attempts/{r['id']}/review",
                      {"scores": {c: 1.0 for c in criteria}, "feedback": "Clear grounding and escalation rules."}).json()
    assert done["status"] == "reviewed" and done["points_awarded"] == 25
    attempts = learner.get("/challenges/prompt-rewrite-support-bot/attempts").json()["items"]
    assert attempts[0]["review_feedback"].startswith("Clear grounding")


def test_daily_is_deterministic(api):
    assert api.get("/challenges/daily").json()["slug"] == api.get("/challenges/daily").json()["slug"]


def test_attempts_require_auth(api):
    assert api.post("/challenges/py-two-sum/attempts", {"code": "x"}).status_code == 401
