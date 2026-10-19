from ..core import AgentSpec
from .agent import InvoiceExtractionInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_INVOICE = """Northwind Cloud Services Ltd.
221B Market Street, Bengaluru 560001
GSTIN 29ABCDE1234F1Z5

INVOICE
Invoice No: NW-2026-0042
Invoice Date: 2026-02-01
Due Date: 2026-03-03
Bill To: AgentForge Academy

Description                     Qty   Unit Price     Amount
Managed PostgreSQL (db.m6)        2       180.00     360.00
Object storage 2TB                1        46.00      46.00
Support plan - Business           1       150.00     150.00

Subtotal                                             556.00
GST 18%                                              100.08
Total Due                                     USD    656.08
"""

SPEC = AgentSpec(
    slug="invoice-extraction-agent",
    name="Invoice Extraction Agent",
    input_model=InvoiceExtractionInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[{"text": EXAMPLE_INVOICE}],
    blueprint=BLUEPRINT,
    package=__name__,
)
