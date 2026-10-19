from ..core import AgentSpec
from .agent import CSVCleaningInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_CSV = """id,name,email,signup_date,plan,monthly_spend,active
1, Asha Iyer ,ASHA@Example.com,15/01/2025,pro,"$1,200.00",yes
2,Ben Smith,ben@example,02/02/2025,Pro,$89.50,Y
3,Chen Wang,chen@example.com,28/02/2025,free,N/A,no
4,Diego Garcia,diego@example.com,03/03/2025,FREE,$0,n
4,Diego Garcia,diego@example.com,03/03/2025,FREE,$0,n
5,Elena Muller,elena@example.com,,team,"$2,450.00",true
,,,,,,
6,Farah Khan,farah@example.com,10/03/2025,Team,null,false
"""

SPEC = AgentSpec(
    slug="csv-cleaning-agent",
    name="CSV Cleaning Agent",
    input_model=CSVCleaningInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[{"csv_text": EXAMPLE_CSV, "goals": "Monthly revenue reporting by plan"}],
    blueprint=BLUEPRINT,
    package=__name__,
)
