import shutil

import pytest
from fastapi.testclient import TestClient

from runner import app as app_module
from runner.executor import execute

has_node = shutil.which("node") is not None


def test_python_stdout():
    r = execute("python", "print('hi', 2 + 3)")
    assert r.status == "ok" and r.stdout.strip() == "hi 5"


def test_python_tests_pass_and_fail():
    code = "def add(a, b):\n    print('debug')\n    return a + b\n"
    r = execute("python", code, tests={"function": "add", "cases": [{"args": [1, 2], "expected": 3}, {"args": [1, 1], "expected": 3}]})
    assert r.tests["passed"] == 1 and r.tests["total"] == 2
    assert "debug" in r.stdout and "__AFRESULT" not in r.stdout


def test_python_compile_error_reported():
    r = execute("python", "def broken(:", tests={"function": "x", "cases": [{"args": [], "expected": 1}]})
    assert r.status == "error" and "SyntaxError" in r.tests["compile_error"]


def test_infinite_loop_times_out():
    r = execute("python", "while True:\n    pass\n", timeout_ms=800)
    assert r.timed_out and r.status == "timeout"


def test_memory_bomb_is_killed():
    r = execute("python", "x = bytearray(2 * 1024 * 1024 * 1024)\nprint('allocated')")
    assert "allocated" not in r.stdout and r.status in ("error", "killed")


def test_output_flood_is_capped():
    r = execute("python", "while True:\n    print('x' * 1000)\n", timeout_ms=2000)
    assert len(r.stdout) <= 64 * 1024


def test_environment_is_scrubbed(monkeypatch):
    monkeypatch.setenv("SECRET_SHOULD_NOT_LEAK", "s3cr3t")
    r = execute("python", "import os\nprint(os.environ.get('SECRET_SHOULD_NOT_LEAK'))")
    assert r.stdout.strip() == "None"


def test_forged_result_line_is_ignored():
    code = "def f():\n    print('__AFRESULT_deadbeef__{\"results\": [{\"passed\": true}]}')\n    return 0\n"
    r = execute("python", code, tests={"function": "f", "cases": [{"args": [], "expected": 1}]})
    assert r.tests["passed"] == 0


def test_sql_run_and_test_modes():
    setup = "CREATE TABLE t(a INT, b TEXT); INSERT INTO t VALUES (1,'x'),(2,'y');"
    r = execute("sql", "SELECT b FROM t ORDER BY a;", sql_setup=setup)
    assert r.sql["rows"] == [["x"], ["y"]]
    r = execute("sql", "SELECT a FROM t", sql_setup=setup, sql_expected={"expected_rows": [[2], [1]], "ordered": False})
    assert r.tests["passed"] == 1
    r = execute("sql", "SELECT nope FROM t", sql_setup=setup, sql_expected={"expected_rows": [[1]]})
    assert "no such column" in r.tests["compile_error"]


@pytest.mark.skipif(not has_node, reason="node not installed")
def test_javascript_run_and_tests():
    r = execute("javascript", "console.log([1,2].map(x => x * 2))")
    assert r.stdout.strip() == "[2,4]"
    code = "function sum(xs) { return xs.reduce((a, b) => a + b, 0); }"
    r = execute("javascript", code, tests={"function": "sum", "cases": [{"args": [[1, 2, 3]], "expected": 6}]})
    assert r.tests["passed"] == 1


@pytest.mark.skipif(not has_node, reason="node not installed")
def test_javascript_infinite_loop():
    r = execute("javascript", "function f(){ while(true){} }", timeout_ms=3000,
                tests={"function": "f", "cases": [{"args": [], "expected": 1}]})
    assert r.tests["passed"] == 0


def test_http_api_requires_token(monkeypatch):
    monkeypatch.setattr(app_module, "TOKEN", "t0k")
    monkeypatch.setattr(app_module, "ALLOW_NO_TOKEN", False)
    client = TestClient(app_module.app)
    assert client.post("/v1/run", json={"language": "python", "code": "print(1)"}).status_code == 401
    ok = client.post("/v1/run", json={"language": "python", "code": "print(1)"}, headers={"X-Sandbox-Token": "t0k"})
    assert ok.status_code == 200 and ok.json()["stdout"].strip() == "1"
