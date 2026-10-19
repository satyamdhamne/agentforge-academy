"""Offline responder: derives tests from docstring examples, explicit raise conditions and type hints."""

from __future__ import annotations

import re

from ..core import CompletionRequest

SAMPLE_BY_TYPE = {"int": "3", "float": "2.5", "str": "'abc'", "bool": "True", "list": "[1, 2, 3]",
                  "list[int]": "[1, 2, 3]", "list[str]": "['a', 'b']", "dict": "{'a': 1}", "None": "None"}
_CMP = re.compile(r"^(\w+)\s*(<=|<|>=|>|==)\s*(-?\d+(?:\.\d+)?)$")


def _violating_value(op: str, const: str) -> str:
    v = float(const) if "." in const else int(const)
    return {"<": str(v - 1), "<=": str(v), ">": str(v + 1), ">=": str(v), "==": str(v)}[op]


def generate(request: CompletionRequest) -> dict:
    tests = []
    max_tests = request.context.get("max_tests", 4)
    for fn in request.context.get("functions", []):
        name = fn["name"]
        made = []
        for i, ex in enumerate(fn["examples"]):
            made.append({"function": name, "name": f"test_{name}_example_{i + 1}", "kind": "docstring-example",
                         "code": f"def test_{name}_example_{i + 1}():\n    assert {ex['call']} == {ex['expected']}\n"})
        for i, r in enumerate(fn["raises"]):
            m = _CMP.match(r["condition"].replace("not ", ""))
            params = [p["name"] for p in fn["params"]]
            if not m or m.group(1) not in params or "not " in r["condition"]:
                continue
            args = []
            for p in fn["params"]:
                if p["name"] == m.group(1):
                    args.append(_violating_value(m.group(2), m.group(3)))
                else:
                    args.append(p["default"] or SAMPLE_BY_TYPE.get(p["annotation"] or "", "1"))
            made.append({"function": name, "name": f"test_{name}_raises_{i + 1}", "kind": "error-condition",
                         "code": f"def test_{name}_raises_{i + 1}():\n    with pytest.raises({r['exception']}):\n"
                                 f"        {name}({', '.join(args)})\n"})
        if not made:
            args = ", ".join(p["default"] or SAMPLE_BY_TYPE.get(p["annotation"] or "", "1") for p in fn["params"])
            ret = fn.get("returns")
            check = (f"    assert isinstance(result, {ret.split('[')[0]})\n"
                     if ret and ret.split("[")[0] in ("int", "float", "str", "bool", "list", "dict", "tuple", "set") else
                     "    assert result is not None or result is None  # smoke test: call succeeds\n")
            made.append({"function": name, "name": f"test_{name}_smoke", "kind": "smoke",
                         "code": f"def test_{name}_smoke():\n    result = {name}({args})\n{check}"})
        tests.extend(made[:max_tests])
    notes = ["Mock generator: tests come from docstring examples, explicit raise conditions and type hints only. "
             "A real model adds edge cases and property-based checks."]
    return {"tests": tests, "notes": notes}


RESPONDERS = {"unit_test_gen.generate": generate}
