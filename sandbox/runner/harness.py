"""Harness source code written next to the learner's code inside each run directory.

Harnesses read a per-run nonce and the test spec from stdin BEFORE executing learner code, run the
code, evaluate test cases, and print one result line prefixed with the nonce. The runner only trusts
the line carrying the nonce. (Learner code runs in the same process, so a determined learner could
still forge results - points are a learning aid, not a security boundary. Isolation of the *host*
is what the sandbox guarantees.)
"""

PYTHON_HARNESS = r'''
import contextlib, copy, io, json, math, sys, traceback
_nonce = sys.stdin.readline().strip()
_spec = json.loads(sys.stdin.readline())
_real = sys.stdout
_buf = io.StringIO()

def _jsonable(v):
    if isinstance(v, (tuple, list)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted((_jsonable(x) for x in v), key=repr)
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return repr(v)

def _same(a, b, mode):
    if mode == "approx" and isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    if mode == "approx" and isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return all(_same(x, y, mode) for x, y in zip(a, b))
    if mode == "unordered" and isinstance(a, list) and isinstance(b, list):
        return sorted(map(json.dumps, a)) == sorted(map(json.dumps, b))
    return a == b

_out = {"compile_error": None, "results": []}
_ns = {"__name__": "solution"}
try:
    with open("solution.py", encoding="utf-8") as _f:
        _code = compile(_f.read(), "solution.py", "exec")
    with contextlib.redirect_stdout(_buf):
        exec(_code, _ns)
except BaseException:
    _out["compile_error"] = traceback.format_exc(limit=2)[-1500:]
if _out["compile_error"] is None:
    _fn = _ns.get(_spec["function"])
    if not callable(_fn):
        _out["compile_error"] = f"Function '{_spec['function']}' is not defined"
    else:
        for _i, _case in enumerate(_spec["cases"]):
            _r = {"index": _i}
            try:
                with contextlib.redirect_stdout(_buf):
                    _actual = _jsonable(_fn(*copy.deepcopy(_case["args"])))
                _r["actual"] = _actual
                _r["passed"] = _same(_actual, _case["expected"], _spec.get("compare", "exact"))
            except BaseException as _e:
                _r["passed"] = False
                _r["error"] = f"{type(_e).__name__}: {_e}"[:500]
            _out["results"].append(_r)
_real.write(_buf.getvalue()[-20000:])
_real.write("\n" + _nonce + json.dumps(_out) + "\n")
'''

JS_HARNESS = r'''
const fs = require("fs");
const vm = require("vm");
const input = fs.readFileSync(0, "utf8").split("\n");
const nonce = input[0].trim();
const spec = JSON.parse(input[1]);
const logs = [];
const fmt = (a) => a.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
const sandboxConsole = { log: (...a) => logs.push(fmt(a)), error: (...a) => logs.push(fmt(a)), warn: (...a) => logs.push(fmt(a)) };
const ctx = vm.createContext({ console: sandboxConsole });
const out = { compile_error: null, results: [] };
const clone = (v) => JSON.parse(JSON.stringify(v));
const canon = (v) => JSON.stringify(v === undefined ? null : v);
const same = (a, b, mode) => {
  if (mode === "unordered" && Array.isArray(a) && Array.isArray(b))
    return JSON.stringify(a.map(canon).sort()) === JSON.stringify(b.map(canon).sort());
  if (mode === "approx" && typeof a === "number" && typeof b === "number") return Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(b));
  return canon(a) === canon(b);
};
try {
  vm.runInContext(fs.readFileSync("solution.js", "utf8"), ctx, { filename: "solution.js", timeout: 4000 });
} catch (e) {
  out.compile_error = String(e && e.stack ? e.stack.split("\n").slice(0, 3).join("\n") : e);
}
if (!out.compile_error) {
  const fn = ctx[spec.function];
  if (typeof fn !== "function") out.compile_error = `Function '${spec.function}' is not defined (use a function declaration)`;
  else spec.cases.forEach((c, i) => {
    const r = { index: i };
    try {
      ctx.__args = clone(c.args);
      ctx.__fn = fn;
      let actual = vm.runInContext("__fn(...__args)", ctx, { timeout: 2000 });
      actual = actual === undefined ? null : JSON.parse(JSON.stringify(actual));
      r.actual = actual;
      r.passed = same(actual, c.expected, spec.compare || "exact");
    } catch (e) {
      r.passed = false;
      r.error = String(e && e.message ? `${e.name}: ${e.message}` : e).slice(0, 500);
    }
    out.results.push(r);
  });
}
process.stdout.write(logs.join("\n").slice(-20000));
process.stdout.write("\n" + nonce + JSON.stringify(out) + "\n");
'''

JS_RUN = r'''
const fs = require("fs");
const vm = require("vm");
const fmt = (a) => a.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
const out = (...a) => process.stdout.write(fmt(a) + "\n");
const ctx = vm.createContext({ console: { log: out, error: out, warn: out, info: out },
  setTimeout, clearTimeout, setInterval, clearInterval, setImmediate, queueMicrotask, structuredClone });
try {
  vm.runInContext(fs.readFileSync("solution.js", "utf8"), ctx, { filename: "solution.js", timeout: 4500 });
} catch (e) {
  process.stderr.write(String(e && e.stack ? e.stack.split("\n").slice(0, 4).join("\n") : e) + "\n");
  process.exit(1);
}
'''

SQL_HARNESS = r'''
import json, sqlite3, sys
_nonce = sys.stdin.readline().strip()
_spec = json.loads(sys.stdin.readline())
conn = sqlite3.connect(":memory:")
out = {"compile_error": None, "columns": [], "rows": [], "results": []}
try:
    if _spec.get("setup"):
        conn.executescript(_spec["setup"])
    with open("solution.sql", encoding="utf-8") as f:
        sql = f.read().strip()
    if _spec.get("mode") == "test":
        cur = conn.execute(sql.rstrip().rstrip(";"))
        out["columns"] = [d[0] for d in cur.description or []]
        out["rows"] = [list(r) for r in cur.fetchmany(500)]
        exp = _spec["expected_rows"]
        got = out["rows"]
        ok = got == exp if _spec.get("ordered") else sorted(map(json.dumps, got)) == sorted(map(json.dumps, exp))
        if ok and _spec.get("expected_columns"):
            ok = [c.lower() for c in out["columns"]] == [c.lower() for c in _spec["expected_columns"]]
        out["results"].append({"index": 0, "passed": ok, "actual": got[:50]})
    else:
        statements, buf = [], ""
        for line in sql.splitlines(keepends=True):
            buf += line
            if sqlite3.complete_statement(buf):
                statements.append(buf.strip())
                buf = ""
        if buf.strip():
            statements.append(buf.strip())
        for st in statements:
            cur = conn.execute(st)
            if cur.description:
                out["columns"] = [d[0] for d in cur.description]
                out["rows"] = [list(r) for r in cur.fetchmany(200)]
except sqlite3.Error as e:
    out["compile_error"] = f"{type(e).__name__}: {e}"
print(_nonce + json.dumps(out, default=str))
'''
