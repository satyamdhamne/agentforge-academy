import subprocess
import sys

import pytest


@pytest.fixture
def local_runner():
    """TEST ONLY: runs code in a plain subprocess. Not isolated - production uses the sandbox service."""

    def run(req: dict) -> dict:
        p = subprocess.run([sys.executable, "-I", "-c", req["code"]], capture_output=True, text=True, timeout=10)
        return {"stdout": p.stdout, "stderr": p.stderr, "exit_code": p.returncode, "timed_out": False}

    return run
