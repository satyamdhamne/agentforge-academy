"""Every implemented agent must pass 100% of its evaluation dataset with the mock provider."""

import pytest

from agentforge_agents.evals import load_cases, run_eval
from agentforge_agents.registry import IMPLEMENTED, build_blueprint


@pytest.mark.parametrize("slug", sorted(IMPLEMENTED))
def test_eval_dataset_passes(slug):
    spec = IMPLEMENTED[slug]
    assert len(load_cases(spec)) >= 3, "each agent needs at least 3 eval cases"
    report = run_eval(spec)
    failures = [r for r in report["results"] if not r["passed"]]
    assert not failures, failures


@pytest.mark.parametrize("slug", sorted(IMPLEMENTED))
def test_blueprint_has_every_detail_section(slug):
    bp = build_blueprint(IMPLEMENTED[slug])
    required = ["category", "level", "build_hours", "problem", "business_value", "inputs", "outputs", "prerequisites",
                "verdict", "verdict_reasoning", "architecture_mermaid", "data_flow", "framework", "model_selection",
                "prompts", "tools", "state_memory", "folder_structure", "env_vars", "install", "run_local", "tests",
                "evaluation", "security", "cost_latency", "deployment", "observability", "failure_modes",
                "improvements", "production_checklist", "challenges", "interview_questions", "input_schema"]
    missing = [k for k in required if not bp.get(k)]
    assert not missing, missing
    assert len(bp["challenges"]) == 3
    assert bp["verdict"] in {"agent", "workflow", "rag", "deterministic"}


@pytest.mark.parametrize("slug", sorted(IMPLEMENTED))
def test_examples_run(slug):
    from agentforge_agents.core import run_agent

    spec = IMPLEMENTED[slug]
    for example in spec.examples:
        result = run_agent(spec, example)
        assert result.status in ("succeeded", "awaiting_approval"), result.error
        assert result.trace, "every run must produce a trace"
