"""Sandbox runner HTTP service. Reachable only from the backend on an internal network."""

from __future__ import annotations

import asyncio
import hmac
import os
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .executor import execute, languages

TOKEN = os.getenv("SANDBOX_TOKEN", "")
ALLOW_NO_TOKEN = os.getenv("SANDBOX_ALLOW_NO_TOKEN") == "1"
MAX_CONCURRENCY = int(os.getenv("SANDBOX_MAX_CONCURRENCY", str(max(2, (os.cpu_count() or 2)))))
_slots = asyncio.Semaphore(MAX_CONCURRENCY)

app = FastAPI(title="AgentForge Sandbox Runner", version="1.0.0", docs_url=None, redoc_url=None)


class TestCase(BaseModel):
    args: list[Any]
    expected: Any = None


class TestSpec(BaseModel):
    function: str = Field(..., pattern=r"^[A-Za-z_$][A-Za-z0-9_$]*$")
    cases: list[TestCase] = Field(..., max_length=100)
    compare: Literal["exact", "approx", "unordered"] = "exact"


class SQLExpectation(BaseModel):
    expected_rows: list[list[Any]]
    expected_columns: list[str] | None = None
    ordered: bool = False


class RunRequest(BaseModel):
    language: Literal["python", "javascript", "sql"]
    code: str = Field(..., max_length=100_000)
    stdin: str = Field("", max_length=100_000)
    timeout_ms: int = Field(5000, ge=100, le=15_000)
    tests: TestSpec | None = None
    sql_setup: str | None = Field(None, max_length=200_000)
    sql_expected: SQLExpectation | None = None


def _auth(token: str | None) -> None:
    if ALLOW_NO_TOKEN and not TOKEN:
        return
    if not TOKEN or not token or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(status_code=401, detail="invalid sandbox token")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "languages": languages(), "max_concurrency": MAX_CONCURRENCY}


@app.post("/v1/run")
async def run(req: RunRequest, x_sandbox_token: str | None = Header(default=None)) -> dict:
    _auth(x_sandbox_token)
    if req.language == "javascript" and not languages()["javascript"]:
        raise HTTPException(status_code=501, detail="Node.js is not installed in this sandbox")
    if req.tests and req.language == "sql":
        raise HTTPException(status_code=422, detail="use sql_expected for SQL tests")
    async with _slots:
        result = await run_in_threadpool(
            execute, req.language, req.code, req.stdin, req.timeout_ms,
            req.tests.model_dump() if req.tests else None, req.sql_setup,
            req.sql_expected.model_dump() if req.sql_expected else None,
        )
    return result.to_dict()
