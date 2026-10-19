from ..core import AgentSpec, Budget
from .agent import BugTriageInput, apply_actions, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_ISSUE = {
    "title": "Checkout crashes with KeyError for guest users",
    "reporter": "qa-bot",
    "body": """Guest users can't complete checkout since this morning. Error page after clicking Pay.

Traceback (most recent call last):
  File "api/handlers.py", line 88, in post_checkout
    total = pricing.compute_total(cart, user)
  File "checkout/pricing.py", line 41, in compute_total
    currency = user.profile["currency"]
KeyError: 'currency'
""",
}

SPEC = AgentSpec(
    slug="bug-triage-agent",
    name="Bug Triage Agent",
    input_model=BugTriageInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[
        {"issue": EXAMPLE_ISSUE},
        {"issue": {"title": "Report export is very slow", "reporter": "customer-success",
                   "body": "Exporting the quarterly PDF report takes minutes and sometimes times out. Workaround: export by month."}},
    ],
    blueprint=BLUEPRINT,
    package=__name__,
    apply_actions=apply_actions,
    budget=Budget(max_llm_calls=10, max_total_tokens=40_000, max_seconds=60),
)
