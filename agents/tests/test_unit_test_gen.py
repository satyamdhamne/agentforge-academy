from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.unit_test_gen import EXAMPLE_SOURCE, SPEC
from agentforge_agents.unit_test_gen.tools import analyze_source, validate_test


def test_analyze_source_extracts_examples_and_raises():
    fns = {f["name"]: f for f in analyze_source(EXAMPLE_SOURCE)}
    assert len(fns["chunk_text"]["examples"]) == 2
    assert fns["chunk_text"]["raises"][0] == {"condition": "size <= 0", "exception": "ValueError"}


def test_validate_test_rejects_unsafe_code():
    assert validate_test("def test_ok():\n    assert 1 == 1")[1] is None
    assert "import" in validate_test("import os\ndef test_x():\n    os.system('ls')")[1]
    assert "forbidden" in validate_test("def test_x():\n    open('/etc/passwd')")[1]
    assert "dunder" in validate_test("def test_x():\n    ().__class__")[1]
    assert "exactly one" in validate_test("def helper():\n    pass")[1]


def test_generated_tests_execute_in_runner(local_runner):
    out = run_agent(SPEC, SPEC.examples[0], sandbox=local_runner).output
    v = out["validation"]
    assert v["mode"] == "sandbox" and v["passed"] == len(out["tests"]) and v["failed"] == 0


def test_failing_generated_test_is_reported_not_hidden(local_runner):
    bad = {"tests": [{"function": "chunk_text", "name": "t", "code": "def test_wrong():\n    assert chunk_text(['a'], 1) == []"}]}
    out = run_agent(SPEC, SPEC.examples[0], provider=MockProvider({"unit_test_gen.generate": lambda r: bad}), sandbox=local_runner).output
    assert out["validation"]["failed"] == 1


def test_without_sandbox_tests_are_not_run():
    out = run_agent(SPEC, SPEC.examples[0]).output
    assert out["validation"]["mode"] == "not_run"
