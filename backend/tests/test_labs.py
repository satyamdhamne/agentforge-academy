"""Phase 4: prompt lab, RAG lab, evaluations and the LLM/SLM lab."""

from __future__ import annotations

import base64

# ------------------------------------------------------------------ prompt lab

def test_template_catalog_and_detail(api):
    d = api.get("/prompts/templates").json()
    slugs = {t["slug"] for t in d["items"]}
    assert {"ticket-classifier", "invoice-extraction", "injection-safe-summary", "grounded-answer"} <= slugs
    t = api.get("/prompts/templates/ticket-classifier").json()
    assert len(t["versions"]) == 2 and t["versions"][0]["version"] == 2 and t["test_cases"]
    assert t["editable"] is False


def test_playground_run_uses_simulator_on_free_plan(learner):
    r = learner.post("/prompts/run", {"system": "Classify the ticket. Respond with one of: billing, bug, account.",
                                      "user_template": "Ticket: {{ticket}}", "variables": {"ticket": "The app crashes with error 500"},
                                      "assertions": [{"type": "equals", "value": "bug"}]}).json()
    assert r["output"] == "bug" and r["mode"] == "mock" and r["provider"] == "mock" and r["cost_usd"] == 0
    assert r["checks"]["passed"] == 1
    missing = learner.post("/prompts/run", {"user_template": "Hi {{name}}", "variables": {}})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "missing_variables"


def test_ab_compare_shows_injection_defense_wins(learner):
    t = learner.get("/prompts/templates/injection-safe-summary").json()
    v2, v1 = t["versions"][0], t["versions"][1]
    r = learner.post("/prompts/compare", {"template_slug": "injection-safe-summary", "variants": [
        {"label": "naive", "system": v1["system"], "user_template": v1["user_template"]},
        {"label": "defended", "system": v2["system"], "user_template": v2["user_template"]}]}).json()
    by = {s["label"]: s for s in r["summary"]}
    assert by["defended"]["pass_rate"] > by["naive"]["pass_rate"]
    assert r["best"] == "defended"
    leaked = [m for m in r["matrix"] if m["variant"] == 0 and "SAVE50" in m["output"]]
    assert leaked, "the naive prompt should fall for the injection in the simulator"
    ev = learner.get(f"/evaluations/{r['evaluation_id']}").json()
    assert ev["target_type"] == "prompt" and len(ev["cases"]) == len(r["matrix"])


def test_structured_output_version_fixes_json(learner):
    t = learner.get("/prompts/templates/invoice-extraction").json()
    v2, v1 = t["versions"][0], t["versions"][1]
    r = learner.post("/prompts/compare", {"template_slug": "invoice-extraction", "variants": [
        {"label": "prose", "system": v1["system"], "user_template": v1["user_template"]},
        {"label": "schema", "system": v2["system"], "user_template": v2["user_template"], "params": v2["params"]}]}).json()
    by = {s["label"]: s for s in r["summary"]}
    assert by["schema"]["pass_rate"] == 1.0 and by["prose"]["pass_rate"] < 1.0


def test_fork_version_and_test_cases(learner, app):
    from tests.conftest import Api

    slug = learner.post("/prompts/templates/support-reply/fork").json()["slug"]
    assert slug.startswith("support-reply--")
    v = learner.post(f"/prompts/templates/{slug}/versions", {"system": "Be brief.", "user_template": "Ticket: {{ticket}}",
                                                             "change_note": "Shorter"}).json()
    assert v["version"] == 2 and v["variables"] == ["ticket"]
    assert learner.put(f"/prompts/templates/{slug}/test-cases", {"cases": [
        {"name": "x", "variables": {"ticket": "hi"}, "assertions": [{"type": "max_words", "value": 50}]}]}).status_code == 200
    assert learner.get(f"/prompts/templates/{slug}").json()["editable"] is True
    other = Api(app)
    other.register()
    assert other.get(f"/prompts/templates/{slug}").status_code == 404  # private to its owner
    assert learner.post("/prompts/templates/support-reply/versions", {"user_template": "x", "change_note": "nope"}).status_code == 403


# ------------------------------------------------------------------ RAG lab

def test_rag_options_and_dataset(api):
    o = api.get("/rag/options").json()
    assert {c["key"] for c in o["chunkers"]} == {"fixed", "recursive", "markdown"}
    assert o["embedders"][0]["key"] == "hashing-384" and o["embedders"][0]["available"]
    d = api.get("/rag/datasets/northwind-handbook").json()
    assert len(d["documents"]) == 9 and len(d["questions"]) == 12
    restricted = next(x for x in d["documents"] if x["source"] == "compensation-bands-2026")
    assert restricted["readable"] is False and restricted["preview"] is None


def test_rag_query_answers_with_citations(learner):
    r = learner.post("/rag/query", {"dataset": "northwind-handbook", "question": "How many API requests per minute can a key send?"}).json()
    assert r["retrieved"][0]["source"] == "api-rate-limits"
    g = r["generation"]
    assert "100" in g["answer"] and g["citations"] and g["grounded"]
    assert {s["stage"] for s in r["stages"]} >= {"index", "permission filter", "retrieve (hybrid)", "rerank", "generate"}


def test_rag_permissions_enforced_in_retrieval(learner, admin):
    q = {"dataset": "northwind-handbook", "question": "What is the E5 salary band?", "strategy": "keyword"}
    r = learner.post("/rag/query", q).json()
    assert all(h["source"] != "compensation-bands-2026" for h in r["retrieved"])
    assert "don't know" in r["generation"]["answer"]
    a = admin.post("/rag/query", q).json()  # admins are in the hr group
    assert a["retrieved"][0]["source"] == "compensation-bands-2026"


def test_rag_injection_in_document_is_ignored_with_default_prompt(learner):
    q = {"dataset": "northwind-handbook", "question": "What do the vendor integration notes say?", "top_k": 4}
    safe = learner.post("/rag/query", q).json()["generation"]["answer"]
    assert "hunter2" not in safe
    unsafe = learner.post("/rag/query", {**q, "system_prompt": "Answer the question using the passages."}).json()["generation"]["answer"]
    assert "hunter2" in unsafe  # removing the defense lets the planted instruction through


def test_rag_evaluate_compares_strategies(learner):
    base = {"dataset": "northwind-handbook", "top_k": 3}
    hybrid = learner.post("/rag/evaluate", {**base, "strategy": "hybrid"}).json()
    assert hybrid["total"] == 12 and hybrid["metrics"]["recall@3"] >= 0.8
    fixed_small = learner.post("/rag/evaluate", {**base, "strategy": "vector", "chunker": "fixed", "size": 20, "overlap": 0,
                                                 "rerank": False}).json()
    assert fixed_small["metrics"]["mrr"] <= hybrid["metrics"]["mrr"]
    cmp = learner.get(f"/evaluations/{fixed_small['evaluation_id']}/compare/{hybrid['evaluation_id']}").json()
    assert any(m["metric"] == "mrr" for m in cmp["metrics"])
    hist = learner.get("/evaluations", params={"target_type": "rag"}).json()["items"]
    assert len(hist) >= 2


def test_rag_upload_and_delete(learner):
    ds = learner.post("/rag/datasets", {"name": "My notes"}).json()
    r = learner.post(f"/rag/datasets/{ds['id']}/documents", {"title": "Deploy notes", "filename": "deploy.md",
                                                              "text": "# Deploys\nWe deploy every Tuesday at 14:00 UTC after the CAB review."})
    assert r.status_code == 201
    dup = learner.post(f"/rag/datasets/{ds['id']}/documents", {"title": "Again", "filename": "deploy.md",
                                                                "text": "# Deploys\nWe deploy every Tuesday at 14:00 UTC after the CAB review."})
    assert dup.status_code == 409
    bad_group = learner.post(f"/rag/datasets/{ds['id']}/documents", {"title": "Secret", "text": "hr only words here for test",
                                                                      "allowed_groups": ["hr"]})
    assert bad_group.status_code == 422  # learners can't restrict to groups they aren't in
    not_pdf = learner.post(f"/rag/datasets/{ds['id']}/documents", {"title": "x", "filename": "x.pdf",
                                                                    "pdf_base64": base64.b64encode(b"hello").decode()})
    assert not_pdf.status_code == 422
    q = learner.post("/rag/query", {"dataset": ds["id"], "question": "When do we deploy?"}).json()
    assert "Tuesday" in q["generation"]["answer"]
    prev = learner.post(f"/rag/datasets/{ds['id']}/chunk-preview", {"document_id": r.json()["id"], "chunker": "fixed", "size": 20}).json()
    assert prev["stats"]["count"] >= 1
    assert learner.c.delete(f"/api/v1/rag/datasets/{ds['id']}/documents/{r.json()['id']}",
                            headers={"X-CSRF-Token": learner.csrf}).status_code == 204


def test_cannot_upload_to_shared_dataset(learner):
    r = learner.post("/rag/datasets/northwind-handbook/documents", {"title": "x", "text": "some words that are long enough"})
    assert r.status_code == 403


# ------------------------------------------------------------------ evaluations & LLM lab

def test_agent_evaluation_is_recorded(learner):
    r = learner.post("/agents/github-pr-review-agent/evaluate").json()
    assert r["pass_rate"] == 1.0
    ev = learner.get(f"/evaluations/{r['evaluation_id']}").json()
    assert ev["summary"]["kind"] == "agent_eval" and len(ev["cases"]) == r["cases"]


def test_llm_lab_catalog_and_providers(api):
    c = api.get("/llm-lab/catalog").json()
    assert len(c["models"]) >= 6 and {t["key"] for t in c["techniques"]} >= {"quantization", "lora", "qlora"}
    p = api.get("/llm-lab/providers").json()
    assert p["you_get"] == "simulator" and "ollama" in p["how_to_run_locally"].lower()


def test_quota_applies_to_prompt_runs(learner):
    from app.core.db import SessionLocal
    from app.models import Entitlement

    with SessionLocal() as db:
        e = db.query(Entitlement).filter_by(plan="free", feature_key="prompt_runs_per_day").one()
        old, e.limit_value = e.limit_value, 1
        db.commit()
    try:
        body = {"user_template": "Text: {{t}}", "variables": {"t": "hello world"}}
        assert learner.post("/prompts/run", body).status_code == 200
        r = learner.post("/prompts/run", body)
        assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"
    finally:
        with SessionLocal() as db:
            db.query(Entitlement).filter_by(plan="free", feature_key="prompt_runs_per_day").one().limit_value = old
            db.commit()
