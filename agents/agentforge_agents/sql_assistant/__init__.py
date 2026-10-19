from ..core import AgentSpec
from .agent import SQLAssistantInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

SPEC = AgentSpec(
    slug="sql-query-assistant",
    name="SQL Query Assistant",
    input_model=SQLAssistantInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[
        {"question": "Who are the top 5 customers by revenue?", "max_rows": 50},
        {"question": "Show monthly revenue", "max_rows": 50},
        {"question": "Which products have never been ordered?", "max_rows": 50},
    ],
    blueprint=BLUEPRINT,
    package=__name__,
)
