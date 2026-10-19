"""python -m app.seed [--no-users] [--skip-agent-runs]"""

from __future__ import annotations

import argparse
import json

from ..core.db import SessionLocal
from .loader import seed_all


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.seed")
    p.add_argument("--no-users", action="store_true", help="Do not create development accounts")
    p.add_argument("--skip-agent-runs", action="store_true", help="Skip example runs and evals (faster)")
    args = p.parse_args()
    with SessionLocal() as db:
        result = seed_all(db, with_users=not args.no_users, with_agent_runs=not args.skip_agent_runs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
