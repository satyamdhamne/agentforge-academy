from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.csv_cleaning import EXAMPLE_CSV, SPEC
from agentforge_agents.csv_cleaning.tools import apply_plan, profile, read_csv, validate_plan


def test_profile_detects_types_and_issues():
    header, rows = read_csv(EXAMPLE_CSV)
    cols = {c["name"]: c for c in profile(header, rows)["columns"]}
    assert cols["monthly_spend"]["type"] == "formatted_number"
    assert cols["signup_date"]["dayfirst"] is True
    assert "invalid_emails" in cols["email"]["issues"]


def test_plan_validation_rejects_unknown_ops_and_columns():
    valid, rejected = validate_plan([{"op": "drop_table"}, {"op": "parse_number", "column": "nope"},
                                     {"op": "trim_whitespace"}], ["a"])
    assert [v["op"] for v in valid] == ["trim_whitespace"]
    assert len(rejected) == 2


def test_apply_plan_logs_changes():
    header, rows, log = apply_plan(["d"], [["01/02/2025"], ["13/02/2025"]], [{"op": "parse_date", "column": "d", "params": {"dayfirst": True}}])
    assert rows == [["2025-02-01"], ["2025-02-13"]] and log[0]["changed"] == 2


def test_model_cannot_run_arbitrary_operations():
    evil = {"steps": [{"op": "exec_python", "params": {"code": "import os"}}, {"op": "trim_whitespace"}]}
    out = run_agent(SPEC, {"csv_text": EXAMPLE_CSV}, provider=MockProvider({"csv_cleaning.plan": lambda r: evil})).output
    assert out["rejected_steps"][0]["op"] == "exec_python"
    assert [s["op"] for s in out["plan"]] == ["trim_whitespace"]
