"""Static analysis of Python source and safety checks for generated tests."""

from __future__ import annotations

import ast
import json
import textwrap

FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "getattr", "setattr",
                   "delattr", "input", "breakpoint", "exit", "quit"}
ALLOWED_IMPORTS = {"pytest", "math"}


def _annotation(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def analyze_source(source: str) -> list[dict]:
    """Describe public top-level functions: signature, docstring examples and explicit raise conditions."""
    tree = ast.parse(source)
    functions = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        args = node.args.args
        defaults = [None] * (len(args) - len(node.args.defaults)) + [ast.unparse(d) for d in node.args.defaults]
        params = [{"name": a.arg, "annotation": _annotation(a.annotation), "default": d} for a, d in zip(args, defaults)]
        doc = ast.get_docstring(node) or ""
        examples = []
        lines = doc.splitlines()
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith(">>> ") and i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith(">>>"):
                examples.append({"call": s[4:], "expected": lines[i + 1].strip()})
        raises = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and sub.body and isinstance(sub.body[0], ast.Raise) and sub.body[0].exc is not None:
                exc = sub.body[0].exc
                exc_name = ast.unparse(exc.func if isinstance(exc, ast.Call) else exc)
                raises.append({"condition": ast.unparse(sub.test), "exception": exc_name})
        branches = sum(isinstance(s, (ast.If, ast.For, ast.While, ast.Try, ast.IfExp, ast.BoolOp)) for s in ast.walk(node))
        functions.append({
            "name": node.name, "params": params, "returns": _annotation(node.returns), "docstring": doc[:500],
            "examples": examples, "raises": raises, "complexity": branches + 1,
        })
    return functions


def validate_test(code: str) -> tuple[str | None, str | None]:
    """Return (test_name, None) if the generated test is acceptable, else (None, reason)."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError as exc:
        return None, f"syntax error: {exc.msg}"
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(funcs) != 1 or not funcs[0].name.startswith("test_"):
        return None, "must define exactly one function named test_*"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(m.split(".")[0] not in ALLOWED_IMPORTS for m in mods):
                return None, f"import not allowed: {mods}"
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            return None, f"forbidden name: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return None, "dunder attribute access not allowed"
    return funcs[0].name, None


PYTEST_SHIM = '''
import math as _math, json as _json, traceback as _tb
class _Raises:
    def __init__(self, exc, match=None): self.exc, self.match = exc, match
    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if et is None: raise AssertionError(f"DID NOT RAISE {self.exc.__name__}")
        if not issubclass(et, self.exc): return False
        if self.match is not None:
            import re as _re
            if not _re.search(self.match, str(ev)): raise AssertionError(f"message {ev!r} does not match {self.match!r}")
        return True
class _Approx:
    def __init__(self, v, rel=1e-6, abs=1e-12): self.v, self.rel, self.abs = v, rel, abs
    def __eq__(self, o): return _math.isclose(o, self.v, rel_tol=self.rel, abs_tol=self.abs)
    def __repr__(self): return f"approx({self.v})"
class pytest:  # minimal pytest-compatible shim so tests run in the sandbox without installing pytest
    raises = _Raises
    approx = _Approx
'''

RUNNER = '''
_results = []
for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        try:
            _fn(); _results.append({"name": _name, "status": "passed"})
        except AssertionError as _e:
            _results.append({"name": _name, "status": "failed", "error": str(_e)[:300]})
        except Exception as _e:
            _results.append({"name": _name, "status": "error", "error": f"{type(_e).__name__}: {_e}"[:300]})
print("__AF_TESTS__" + _json.dumps(_results))
'''


def build_test_file(module_name: str, tests: list[str]) -> str:
    header = f"import pytest\nfrom {module_name} import *  # noqa: F403\n\n"
    return header + "\n\n".join(textwrap.dedent(t).strip() + "\n" for t in tests)


def build_sandbox_script(source: str, tests: list[str]) -> str:
    """Source + shim + tests + runner in one file, executed by the isolated sandbox service."""
    body = "\n\n".join(textwrap.dedent(t).strip() for t in tests)
    return f"{source}\n\n{PYTEST_SHIM}\n\n{body}\n\n{RUNNER}"


def parse_sandbox_result(result: dict) -> dict:
    stdout = result.get("stdout", "")
    marker = stdout.rfind("__AF_TESTS__")
    if marker < 0:
        return {"mode": "sandbox", "passed": 0, "failed": 0, "errors": 1, "results": [],
                "output": (result.get("stderr") or stdout)[-2000:], "timed_out": result.get("timed_out", False)}
    results = json.loads(stdout[marker + len("__AF_TESTS__"):].splitlines()[0])
    return {
        "mode": "sandbox",
        "passed": sum(r["status"] == "passed" for r in results),
        "failed": sum(r["status"] == "failed" for r in results),
        "errors": sum(r["status"] == "error" for r in results),
        "results": results,
        "output": stdout[:marker][-2000:],
        "timed_out": result.get("timed_out", False),
    }
