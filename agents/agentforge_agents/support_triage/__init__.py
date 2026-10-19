from ..core import AgentSpec
from .agent import SupportTriageInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

SPEC = AgentSpec(
    slug="customer-support-triage-agent",
    name="Customer Support Triage Agent",
    input_model=SupportTriageInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[
        {"ticket": {"subject": "Charged twice this month!!", "customer_tier": "pro", "channel": "email",
                    "body": "Hi, I was double charged on my card 4111 1111 1111 1111 for the March invoice. "
                            "This is the second time - really frustrated. Please refund one charge. "
                            "You can reach me at maria.lopez@example.com or +1 415 555 0134."}},
        {"ticket": {"subject": "Dashboard down for all users", "customer_tier": "enterprise", "channel": "chat",
                    "body": "Our production dashboard has been down for 20 minutes, all users see a timeout. Urgent!"}},
    ],
    blueprint=BLUEPRINT,
    package=__name__,
)
