from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.support_triage import SPEC


def _run(body, provider=None, tier="free"):
    return run_agent(SPEC, {"ticket": {"subject": "s", "body": body, "customer_tier": tier}}, provider=provider).output


def test_pii_is_redacted_before_model_call():
    seen = []

    def responder(req):
        seen.append(req.messages[-1].content)
        return {"category": "billing", "priority": "P3", "sentiment": "neutral", "confidence": 0.9, "summary": "s"}

    _run("my email is jane@corp.com and card 4111 1111 1111 1111", MockProvider({"support_triage.classify": responder}))
    assert "jane@corp.com" not in seen[0] and "4111" not in seen[0]


def test_policy_overrides_model():
    lazy = MockProvider({"support_triage.classify": lambda r: {"category": "how_to", "priority": "P4", "sentiment": "neutral",
                                                               "confidence": 0.9, "summary": "s"}})
    out = _run("Someone hacked my account and changed the email", lazy)
    assert out["category"] == "security" and out["priority"] == "P2" and out["needs_human"]
    assert len(out["policy_overrides"]) == 2


def test_low_confidence_goes_to_human():
    unsure = MockProvider({"support_triage.classify": lambda r: {"category": "other", "priority": "P4", "sentiment": "neutral",
                                                                 "confidence": 0.3, "summary": "s"}})
    assert _run("hmm", unsure)["needs_human"] is True
