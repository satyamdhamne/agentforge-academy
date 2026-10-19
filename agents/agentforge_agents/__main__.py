"""CLI: python -m agentforge_agents [list | run <slug> | eval <slug|all>]"""

from __future__ import annotations

import argparse
import json
import sys

from .core import provider_from_env, run_agent
from .evals import run_eval
from .registry import IMPLEMENTED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentforge_agents")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_run = sub.add_parser("run")
    p_run.add_argument("slug")
    p_run.add_argument("--example", type=int, default=0)
    p_run.add_argument("--input", help="Path to a JSON input file (overrides --example)")
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("slug", help="agent slug or 'all'")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for slug, spec in IMPLEMENTED.items():
            print(f"{slug:40s} {spec.blueprint['verdict']:14s} {spec.name}")
        return 0

    if args.cmd == "run":
        spec = IMPLEMENTED.get(args.slug)
        if not spec:
            print(f"Unknown agent {args.slug}", file=sys.stderr)
            return 2
        raw = json.load(open(args.input)) if args.input else spec.examples[args.example]
        result = run_agent(spec, raw, provider=provider_from_env(spec.mock_responders))
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0 if result.status != "failed" else 1

    slugs = list(IMPLEMENTED) if args.slug == "all" else [args.slug]
    failed = 0
    for slug in slugs:
        spec = IMPLEMENTED[slug]
        report = run_eval(spec, provider=provider_from_env(spec.mock_responders))
        print(f"{slug}: {report['passed']}/{report['cases']} passed")
        for r in report["results"]:
            if not r["passed"]:
                failed += 1
                print(f"  FAIL {r['id']} ({r['status']}) {r.get('error') or ''}")
                for c in r["checks"]:
                    if not c["passed"]:
                        print(f"     - {c['check']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
