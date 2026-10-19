"""Process-level execution with resource limits.

Defense in depth - this module is ONE layer. The container adds the others (see docker-compose.yml):
  * no network (internal-only Docker network), read-only root filesystem, tmpfs scratch space
  * non-root user, all Linux capabilities dropped, no-new-privileges, pids limit, memory/CPU limits
This module adds per-run limits: CPU seconds, address space, file size, open files, wall-clock
timeout (whole process group is killed), a scrubbed environment and a fresh temp directory.
"""

from __future__ import annotations

import json
import os
import resource
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from .harness import JS_HARNESS, JS_RUN, PYTHON_HARNESS, SQL_HARNESS

MAX_OUTPUT_BYTES = 64 * 1024
FILE_SIZE_LIMIT = 1024 * 1024
MEMORY_LIMIT = int(os.getenv("SANDBOX_MEMORY_BYTES", str(512 * 1024 * 1024)))
PYTHON = os.getenv("SANDBOX_PYTHON", shutil.which("python3") or "python3")
NODE = os.getenv("SANDBOX_NODE", shutil.which("node") or "node")


@dataclass
class RunResult:
    status: str  # ok | error | timeout | killed
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    timed_out: bool
    truncated: bool
    tests: dict[str, Any] | None = None
    sql: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None or k in ("exit_code",)}


def languages() -> dict[str, bool]:
    return {"python": bool(shutil.which(PYTHON) or os.path.exists(PYTHON)), "sql": True,
            "javascript": bool(shutil.which(NODE) or os.path.exists(NODE))}


def _limits(cpu_seconds: int, limit_memory: bool):
    def apply() -> None:
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_LIMIT, FILE_SIZE_LIMIT))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if limit_memory:  # V8 reserves large virtual ranges, so Node relies on --max-old-space-size + container limits
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    return apply


def _read_capped(path: str) -> tuple[str, bool]:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        data = f.read(MAX_OUTPUT_BYTES)
    return data.decode("utf-8", errors="replace"), size > MAX_OUTPUT_BYTES


def execute(language: str, code: str, stdin: str = "", timeout_ms: int = 5000, tests: dict | None = None,
            sql_setup: str | None = None, sql_expected: dict | None = None) -> RunResult:
    if language not in ("python", "javascript", "sql"):
        raise ValueError(f"unsupported language {language}")
    timeout_s = max(0.5, min(timeout_ms, 15_000) / 1000)
    workdir = tempfile.mkdtemp(prefix="run-")
    nonce = "__AFRESULT_" + secrets.token_hex(8) + "__"
    try:
        harness_input = None
        if language == "python":
            with open(os.path.join(workdir, "solution.py"), "w", encoding="utf-8") as f:
                f.write(code)
            if tests:
                with open(os.path.join(workdir, "harness.py"), "w") as f:
                    f.write(PYTHON_HARNESS)
                cmd = [PYTHON, "-I", "-B", "harness.py"]
                harness_input = f"{nonce}\n{json.dumps(tests)}\n"
            else:
                cmd = [PYTHON, "-I", "-B", "solution.py"]
        elif language == "javascript":
            with open(os.path.join(workdir, "solution.js"), "w", encoding="utf-8") as f:
                f.write(code)
            with open(os.path.join(workdir, "harness.js"), "w") as f:
                f.write(JS_HARNESS if tests else JS_RUN)
            cmd = [NODE, "--max-old-space-size=96", "--disallow-code-generation-from-strings", "harness.js"]
            if tests:
                harness_input = f"{nonce}\n{json.dumps(tests)}\n"
        else:
            with open(os.path.join(workdir, "solution.sql"), "w", encoding="utf-8") as f:
                f.write(code)
            with open(os.path.join(workdir, "harness.py"), "w") as f:
                f.write(SQL_HARNESS)
            cmd = [PYTHON, "-I", "-B", "harness.py"]
            spec = {"setup": sql_setup or "", "mode": "test" if sql_expected else "run", **(sql_expected or {})}
            harness_input = f"{nonce}\n{json.dumps(spec)}\n"

        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": workdir, "LANG": "C.UTF-8", "PYTHONHASHSEED": "0",
               "PYTHONDONTWRITEBYTECODE": "1", "NODE_OPTIONS": ""}
        out_path, err_path = os.path.join(workdir, ".stdout"), os.path.join(workdir, ".stderr")
        started = time.perf_counter()
        timed_out = False
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            proc = subprocess.Popen(cmd, cwd=workdir, env=env, stdin=subprocess.PIPE, stdout=out_f, stderr=err_f,
                                    preexec_fn=_limits(int(timeout_s) + 1, language != "javascript"), close_fds=True)
            try:
                proc.communicate(input=(harness_input or stdin).encode()[: 1024 * 1024], timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        duration = int((time.perf_counter() - started) * 1000)
        stdout, t1 = _read_capped(out_path)
        stderr, t2 = _read_capped(err_path)
        code_ = proc.returncode
        status = "timeout" if timed_out else "ok" if code_ == 0 else "killed" if code_ is not None and code_ < 0 else "error"
        if code_ == -signal.SIGXCPU:
            status, timed_out = "timeout", True
        result = RunResult(status, stdout, stderr[-8000:], code_, duration, timed_out, t1 or t2)
        if harness_input is not None:
            idx = stdout.rfind(nonce)
            parsed = None
            if idx >= 0:
                try:
                    parsed = json.loads(stdout[idx + len(nonce):].splitlines()[0])
                except (json.JSONDecodeError, IndexError):
                    parsed = None
            result.stdout = stdout[:idx].rstrip("\n") if idx >= 0 else stdout
            if parsed is None:
                if result.status == "ok":
                    result.status = "error"
                parsed = {"compile_error": "No result produced (crashed, killed or timed out)", "results": []}
            if language == "sql":
                result.sql = {"columns": parsed.get("columns", []), "rows": parsed.get("rows", [])}
            if tests or sql_expected or language == "sql":
                rs = parsed.get("results", [])
                result.tests = {"compile_error": parsed.get("compile_error"), "results": rs,
                                "passed": sum(1 for r in rs if r.get("passed")), "total": len(rs)}
                if parsed.get("compile_error") and result.status == "ok":
                    result.status = "error"
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
