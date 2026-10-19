import pytest

from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.sql_assistant import SPEC
from agentforge_agents.sql_assistant.tools import SQLGuardError, build_demo_db, execute_readonly


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "SELECT 1; DROP TABLE orders",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "SELECT load_extension('evil')",
    "PRAGMA table_info(orders)",
])
def test_destructive_or_unsafe_sql_is_blocked(sql):
    with pytest.raises(SQLGuardError):
        execute_readonly(build_demo_db(), sql)


def test_runaway_query_times_out():
    sql = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT count(*) FROM r"
    with pytest.raises(SQLGuardError, match="time limit"):
        execute_readonly(build_demo_db(), sql, timeout_s=0.3)


def test_row_cap_reports_truncation():
    res = execute_readonly(build_demo_db(), "SELECT * FROM order_items", max_rows=10)
    assert res["row_count"] == 10 and res["truncated"] is True


def test_self_correction_loop_recovers_from_bad_sql():
    attempts = []

    def responder(req):
        attempts.append(req.context["last_error"])
        if len(attempts) == 1:
            return {"sql": "SELECT nme FROM customers", "explanation": "typo"}
        return {"sql": "SELECT name FROM customers LIMIT 3", "explanation": "fixed"}

    out = run_agent(SPEC, {"question": "names"}, provider=MockProvider({"sql_assistant.generate": responder})).output
    assert out["row_count"] == 3
    assert out["attempts"][0]["error"] and "nme" in out["attempts"][0]["error"]
    assert attempts[1] is not None  # second attempt saw the database error


def test_gives_up_after_three_attempts():
    provider = MockProvider({"sql_assistant.generate": lambda r: {"sql": "DROP TABLE orders"}})
    out = run_agent(SPEC, {"question": "drop it"}, provider=provider).output
    assert len(out["attempts"]) == 3 and out["rows"] == []
