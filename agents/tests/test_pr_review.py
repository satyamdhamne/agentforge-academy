from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.pr_review import EXAMPLE_DIFF, SPEC
from agentforge_agents.pr_review.agent import ModelReview, ReviewComment, _apply_guardrails
from agentforge_agents.pr_review.tools import Finding, parse_diff, run_rules


def test_parse_diff_tracks_new_line_numbers():
    files = parse_diff(EXAMPLE_DIFF)
    assert files[0].path == "app/users.py"
    lines = dict(files[0].additions)
    assert 'API_KEY = "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e"' in lines[4]
    assert files[0].deletions == 1


def test_rules_find_expected_issues():
    rules = {f.rule for f in run_rules(parse_diff(EXAMPLE_DIFF))}
    assert {"hardcoded-secret", "sql-injection", "tls-verification-disabled", "missing-tests", "todo"} <= rules


def test_guardrails_drop_hallucinated_lines_and_restore_high_findings():
    files = parse_diff(EXAMPLE_DIFF)
    added = {f.path: {n for n, _ in f.additions} for f in files}
    findings = [Finding("sql-injection", "high", "app/users.py", 7, "SQL", "params")]
    review = ModelReview(summary="ok", verdict="approve", comments=[
        ReviewComment(file="app/users.py", line=999, severity="low", message="invented line"),
        ReviewComment(file="nope.py", line=1, severity="low", message="invented file"),
    ])
    kept, verdict, dropped = _apply_guardrails(review, findings, added)
    assert dropped == 2
    assert verdict == "request_changes"
    assert kept[0].rule == "sql-injection"


def test_model_cannot_approve_when_high_finding_exists():
    provider = MockProvider({"pr_review.review": lambda r: {"summary": "LGTM", "verdict": "approve", "comments": []}})
    out = run_agent(SPEC, SPEC.examples[0], provider=provider).output
    assert out["verdict"] == "request_changes"
    assert any(c["rule"] == "hardcoded-secret" for c in out["comments"])


def test_empty_diff():
    out = run_agent(SPEC, {"diff": "nothing to see here"}).output
    assert out["comments"] == [] and out["stats"]["files_changed"] == 0
