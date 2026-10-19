from ..core import AgentSpec
from .agent import LogAnalysisInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS


def _example_logs() -> str:
    lines = []
    for m in range(10):
        lines.append(f"2026-03-04T09:5{m}:00Z INFO [checkout] GET /api/cart 200 in {40 + m}ms")
    lines.append("2026-03-04T10:00:05Z INFO [checkout] Deployment started: version v2.14.0")
    for m in range(1, 9):
        n = 2 if m < 3 else 18 if m < 6 else 3
        for i in range(n):
            lines.append(f"2026-03-04T10:0{m}:{i:02d}Z ERROR [checkout] QueuePool limit of size 10 overflow 5 reached, "
                         f"connection timed out, timeout 30.00 (request_id=9f1c{i:04x}-aa)")
        lines.append(f"2026-03-04T10:0{m}:30Z WARN [checkout] Slow query took {900 + m * 10}ms: SELECT * FROM orders")
    lines.append("2026-03-04T10:04:10Z ERROR [payments] upstream checkout returned 503 Service Unavailable")
    lines.append("2026-03-04T10:04:11Z ERROR [payments] upstream checkout returned 503 Service Unavailable")
    return "\n".join(lines)


SPEC = AgentSpec(
    slug="log-analysis-agent",
    name="Log Analysis Agent",
    input_model=LogAnalysisInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[{"logs": _example_logs(), "service": ""}],
    blueprint=BLUEPRINT,
    package=__name__,
)
