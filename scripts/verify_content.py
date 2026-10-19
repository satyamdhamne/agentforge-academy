"""Verify seed content: every runnable code example produces its documented output, and every
exercise's reference solution passes its own tests. Runs code through the sandbox executor.

Usage: python scripts/verify_content.py            (from the repo root)
"""

from __future__ import annotations

import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sandbox"))
from runner.executor import execute  # noqa: E402

LESSONS = os.path.join(ROOT, "backend", "app", "seed", "content", "lessons", "*.yaml")
CHALLENGES = os.path.join(ROOT, "backend", "app", "seed", "content", "challenges.yaml")


def norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip("\n").splitlines())


def check_example(lesson: str, ex: dict) -> str | None:
    if not ex.get("runnable"):
        return None
    lang = ex["language"]
    r = execute(lang, ex["code"], sql_setup=ex.get("setup"), timeout_ms=8000)
    if lang == "sql":
        if r.tests and r.tests.get("compile_error"):
            return f"{lesson} / {ex['title']}: SQL error {r.tests['compile_error']}"
        rendered = "\n".join(" | ".join(str(c) for c in row) for row in (r.sql or {}).get("rows", []))
        missing = [line for line in norm(ex["expected_output"]).splitlines() if line not in rendered]
        return f"{lesson} / {ex['title']}: expected lines not found: {missing}\n--- got ---\n{rendered}" if missing else None
    got = norm(r.stdout)
    if r.status != "ok" or got != norm(ex["expected_output"]):
        return f"{lesson} / {ex['title']}: status={r.status}\n--- expected ---\n{norm(ex['expected_output'])}\n--- got ---\n{got}\n{r.stderr[-800:]}"
    return None


def check_exercise(where: str, ex: dict) -> str | None:
    if ex.get("kind", "code") != "code":
        return None
    if ex["language"] == "sql":
        sql = ex["sql"]
        r = execute("sql", ex["solution"], sql_setup=sql["setup"],
                    sql_expected={k: sql[k] for k in ("expected_rows", "expected_columns", "ordered") if k in sql})
    else:
        r = execute(ex["language"], ex["solution"], tests=ex["tests"], timeout_ms=8000)
    t = r.tests or {}
    if t.get("compile_error") or t.get("passed") != t.get("total") or not t.get("total"):
        return f"{where} / exercise {ex['slug']}: {t}"
    # The starter code must NOT already pass (otherwise the exercise is meaningless).
    if ex["language"] != "sql":
        s = execute(ex["language"], ex["starter_code"], tests=ex["tests"], timeout_ms=8000).tests or {}
        if s.get("passed") == s.get("total"):
            return f"{where} / exercise {ex['slug']}: starter code already passes all tests"
    return None


def main() -> int:
    problems = []
    n_examples = n_exercises = 0
    for path in sorted(glob.glob(LESSONS)):
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for ex in doc["sections"]["code_examples"]:
            n_examples += bool(ex.get("runnable"))
            if (p := check_example(doc["slug"], ex)):
                problems.append(p)
        for ex in doc.get("exercises", []):
            n_exercises += 1
            if (p := check_exercise(doc["slug"], ex)):
                problems.append(p)
    if os.path.exists(CHALLENGES):
        with open(CHALLENGES, encoding="utf-8") as fh:
            challenges = yaml.safe_load(fh)["challenges"]
        for ex in challenges:
            n_exercises += 1
            if (p := check_exercise("challenges.yaml", ex)):
                problems.append(p)
    for p in problems:
        print("FAIL:", p, "\n")
    print(f"checked {n_examples} runnable examples and {n_exercises} exercises: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
