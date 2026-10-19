from ..core import AgentSpec
from .agent import PDFKnowledgeInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

SPEC = AgentSpec(
    slug="pdf-knowledge-agent",
    name="PDF Knowledge Agent",
    input_model=PDFKnowledgeInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[
        {"question": "How many PTO days do I get and how many can carry over?"},
        {"question": "How long are application logs retained?"},
        {"question": "What is the salary band for E5?"},
    ],
    blueprint=BLUEPRINT,
    package=__name__,
)
