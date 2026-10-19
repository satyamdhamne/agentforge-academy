from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.invoice_extraction import EXAMPLE_INVOICE, SPEC
from agentforge_agents.invoice_extraction.tools import extract_candidates, validate_invoice


def test_candidates_from_example():
    c = extract_candidates(EXAMPLE_INVOICE)
    assert c["invoice_number"] == "NW-2026-0042" and c["subtotal"] == 556.0 and c["tax"] == 100.08 and c["total"] == 656.08
    assert len(c["line_items"]) == 3


def test_validation_catches_hallucinated_total():
    inv = extract_candidates(EXAMPLE_INVOICE)
    inv["total"] = 999.99
    codes = {i["code"] for i in validate_invoice(inv, EXAMPLE_INVOICE)}
    assert {"ungrounded_total", "total_mismatch"} <= codes


def test_due_date_before_issue_date():
    inv = extract_candidates(EXAMPLE_INVOICE)
    inv["due_date"] = "2026-01-01"
    assert "due_before_issue" in {i["code"] for i in validate_invoice(inv, EXAMPLE_INVOICE + " 2026-01-01")}


def test_model_errors_route_to_review():
    def responder(req):
        out = dict(req.context["candidates"])
        out["invoice_number"] = "INV-INVENTED"
        return out

    out = run_agent(SPEC, {"text": EXAMPLE_INVOICE}, provider=MockProvider({"invoice_extraction.extract": responder})).output
    assert out["status"] == "needs_review"
    assert "ungrounded_invoice_number" in {i["code"] for i in out["issues"]}
