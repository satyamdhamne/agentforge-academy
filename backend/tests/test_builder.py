"""Phase 5: Agent Builder validation, execution, approvals and safety rules."""

from __future__ import annotations


def _create(api, template=None):
    r = api.post("/builder/workflows", {"template": template} if template else {})
    assert r.status_code == 201, r.text
    return r.json()


def test_catalog(api):
    d = api.get("/builder/node-types").json()
    assert {t["type"] for t in d["items"]} == {"input", "prompt", "llm", "tool", "retrieval", "condition", "memory", "human_approval",
                                               "evaluation", "output"}
    assert {t["name"] for t in d["tools"] if t["side_effect"]} == {"send_email", "create_ticket"}
    assert len(api.get("/builder/templates").json()["items"]) == 4


def test_grounded_qa_template_runs(learner):
    wf = _create(learner, "grounded-qa")
    assert not [i for i in wf["issues"] if i["level"] == "error"]
    run = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"question": "How many API requests per minute can a key send?"}}).json()
    assert run["status"] == "succeeded", run["error"]
    assert "100" in run["output"]["result"]["value"] and "[" in run["output"]["result"]["value"]
    assert run["state"]["check"]["passed"] is True
    assert [t["node"] for t in run["trace"]] == ["input", "retrieve", "answer", "check", "result"]
    assert run["mode"] == "mock" and run["llm_calls"] == 1


def test_condition_branches_and_approval_flow(learner):
    wf = _create(learner, "ticket-triage-approval")
    urgent = learner.post(f"/builder/workflows/{wf['id']}/runs",
                          {"input": {"ticket": "Production is down: every API call returns 500 errors, urgent outage!"}}).json()
    assert urgent["status"] == "awaiting_approval", urgent
    assert urgent["pending"]["next_actions"][0]["tool"] == "create_ticket"
    assert urgent["node_status"]["open_incident"] == "pending"
    done = learner.post(f"/builder/runs/{urgent['id']}/decision", {"decision": "approve", "note": "ok"}).json()
    assert done["status"] == "succeeded" and done["state"]["open_incident"]["status"] == "simulated"
    assert done["node_status"]["queue"] == "skipped"

    normal = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"ticket": "Could you add a dark mode feature?"}}).json()
    assert normal["status"] == "succeeded" and normal["node_status"]["approve"] == "skipped"
    assert "Queued" in normal["output"]["normal_out"]["value"]

    again = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"ticket": "URGENT production outage, all customers down"}}).json()
    rejected = learner.post(f"/builder/runs/{again['id']}/decision", {"decision": "reject"}).json()
    assert rejected["status"] == "rejected" and "open_incident" not in rejected["state"]
    assert learner.post(f"/builder/runs/{again['id']}/decision", {"decision": "approve"}).status_code == 409


def test_side_effect_tool_without_approval_is_rejected(learner):
    wf = _create(learner)
    graph = {"name": "unsafe", "nodes": [
        {"key": "input", "type": "input", "config": {"fields": [{"name": "question"}]}},
        {"key": "send", "type": "tool", "config": {"tool": "send_email", "args": {"to": "a@example.com", "subject": "x", "body": "{{input.question}}"}}},
        {"key": "result", "type": "output", "config": {"value": "{{send}}"}}],
        "edges": [{"source": "input", "target": "send"}, {"source": "send", "target": "result"}]}
    saved = learner.put(f"/builder/workflows/{wf['id']}", graph).json()
    assert any("human approval" in i["message"] and i["node"] == "send" for i in saved["issues"])
    r = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"question": "hi"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_workflow"


def test_validation_catches_structural_errors(api):
    def issues(nodes, edges):
        return api.post("/builder/validate", {"name": "x", "nodes": nodes, "edges": edges}).json()

    inp = {"key": "input", "type": "input", "config": {}}
    out = {"key": "result", "type": "output", "config": {"value": "{{later}}"}}
    later = {"key": "later", "type": "prompt", "config": {"template": "hi"}}
    r = issues([inp, out, later], [{"source": "input", "target": "result"}, {"source": "result", "target": "later"}])
    msgs = " ".join(i["message"] for i in r["issues"])
    assert not r["valid"] and "outgoing" in msgs and "doesn't run before" in msgs
    cyc = issues([inp, {"key": "a", "type": "prompt", "config": {"template": "x"}}, {"key": "b", "type": "prompt", "config": {"template": "y"}},
                  {"key": "result", "type": "output", "config": {"value": "x"}}],
                 [{"source": "input", "target": "a"}, {"source": "a", "target": "b"}, {"source": "b", "target": "a"},
                  {"source": "b", "target": "result"}])
    assert "cycle" in " ".join(i["message"] for i in cyc["issues"])
    evil = issues([inp, {"key": "x", "type": "python_exec", "config": {}}, {"key": "result", "type": "output", "config": {"value": "1"}}],
                  [{"source": "input", "target": "result"}])
    assert "Unknown node type" in " ".join(i["message"] for i in evil["issues"])
    tool = issues([inp, {"key": "t", "type": "tool", "config": {"tool": "http_get", "args": {}}}, {"key": "result", "type": "output", "config": {"value": "1"}}],
                  [{"source": "input", "target": "t"}, {"source": "t", "target": "result"}])
    assert "allowlist" in " ".join(i["message"] for i in tool["issues"])


def test_tools_sql_is_read_only_and_calculator_is_safe(learner):
    wf = _create(learner, "revenue-analyst")
    run = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"months": 12}}).json()
    assert run["status"] == "succeeded", run["error"]
    assert run["state"]["revenue"]["rows"][0][0] == 5426.0 and run["state"]["annualised"]["value"] == 32556.0
    g = learner.get(f"/builder/workflows/{wf['id']}").json()
    for n in g["nodes"]:
        if n["key"] == "revenue":
            n["config"]["args"]["sql"] = "DELETE FROM orders"
        if n["key"] == "annualised":
            n["config"]["args"]["expression"] = "__import__('os').system('id')"
    learner.put(f"/builder/workflows/{wf['id']}", {"name": g["name"], "nodes": g["nodes"], "edges": g["edges"]})
    bad = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"months": 12}}).json()
    assert bad["status"] == "failed" and "SQL error" in bad["error"]


def test_required_input_and_budget(learner):
    wf = _create(learner, "grounded-qa")
    r = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {}}).json()
    assert r["status"] == "failed" and "required" in r["error"]


def test_workflows_are_private(learner, app):
    from tests.conftest import Api

    wf = _create(learner, "grounded-qa")
    other = Api(app)
    other.register()
    assert other.get(f"/builder/workflows/{wf['id']}").status_code == 404
    assert other.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"question": "x"}}).status_code == 404


def test_cancel_paused_run(learner):
    wf = _create(learner, "reply-draft-review")
    r = learner.post(f"/builder/workflows/{wf['id']}/runs", {"input": {"email": "I was charged twice", "customer": "dana@example.com"}}).json()
    assert r["status"] == "awaiting_approval" and "dana@example.com" in r["pending"]["message"]
    c = learner.post(f"/builder/runs/{r['id']}/cancel").json()
    assert c["status"] == "cancelled"
