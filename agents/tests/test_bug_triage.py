from agentforge_agents.bug_triage import SPEC
from agentforge_agents.bug_triage.tools import parse_stack_trace, search_similar_issues
from agentforge_agents.core import Budget, Completion, MockProvider, ToolCall, Usage, run_agent


def _completion(name, args):
    return Completion("", [ToolCall("c1", name, args)], Usage(10, 10), "m", "mock")


def test_parse_stack_trace_finds_component():
    t = parse_stack_trace(SPEC.examples[0]["issue"]["body"])
    assert t["exception"] == "KeyError" and t["component"] == "checkout" and t["frames"][-1]["line"] == 41


def test_search_similar_issues():
    assert search_similar_issues("KeyError currency checkout guest")[0]["id"] == "BUG-101"


def test_loop_produces_pending_action_not_a_write():
    r = run_agent(SPEC, SPEC.examples[0])
    assert r.status == "awaiting_approval"
    assert r.output["pending_actions"][0]["tool"] == "apply_triage"
    assert "apply_triage" not in [s["tool"] for s in r.output["steps"]]


def test_model_cannot_call_side_effect_tool():
    provider = MockProvider({"bug_triage.step": lambda r: _completion("apply_triage", {"labels": [], "severity": "low",
                                                                                         "assignee_team": "x", "comment": "hi"})})
    r = run_agent(SPEC, SPEC.examples[0], provider=provider, budget=Budget(max_llm_calls=3))
    assert r.status == "failed" or not r.output["pending_actions"]
    errors = [s.get("result", {}) for s in (r.output or {}).get("steps", [])]
    assert all(e.get("error") for e in errors if isinstance(e, dict))


def test_hallucinated_duplicate_is_cleared():
    calls = iter([
        _completion("finalize_triage", {"severity": "low", "component": "checkout", "labels": ["bug", "made-up"],
                                        "assignee_team": "payments-team", "duplicate_of": "BUG-999", "summary": "s", "reasoning": "r"}),
    ])
    r = run_agent(SPEC, SPEC.examples[0], provider=MockProvider({"bug_triage.step": lambda req: next(calls)}))
    d = r.output["decision"]
    assert d["duplicate_of"] is None and "made-up" not in d["labels"]
    assert len(r.output["guardrail_notes"]) == 2


def test_budget_stops_runaway_loop():
    provider = MockProvider({"bug_triage.step": lambda r: _completion("search_similar_issues", {"query": "loop"})})
    r = run_agent(SPEC, SPEC.examples[0], provider=provider, budget=Budget(max_llm_calls=4))
    assert r.status == "failed" and "BudgetExceeded" in r.error


def test_apply_actions_after_approval():
    r = run_agent(SPEC, SPEC.examples[0])
    res = SPEC.apply_actions(r.output, r.output["pending_actions"])
    assert res["results"][0]["applied"] is True
