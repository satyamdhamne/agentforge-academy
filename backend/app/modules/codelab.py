"""Interactive Code Lab: run code through the isolated sandbox service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..api.deps import DB, CurrentUser, rate_limit
from ..core.errors import AppError
from ..models import UsageEvent, User
from ..services.common import entitlement_limit, plan_for, track
from ..services.sandbox import get_sandbox

router = APIRouter(prefix="/sandbox", tags=["code lab"])


class RunIn(BaseModel):
    language: str = Field(..., pattern="^(python|javascript|sql)$")
    code: str = Field(..., min_length=1, max_length=50_000)
    stdin: str = Field("", max_length=10_000)
    sql_setup: str | None = Field(None, max_length=100_000)


@router.get("/status")
def status() -> dict:
    client = get_sandbox()
    if client is None:
        return {"available": False, "mode": "disabled", "languages": {},
                "message": "Secure code execution is not configured. Examples are read-only until a sandbox runner is connected."}
    st = client.status()
    return {"available": st["available"], "mode": "sandbox" if st["available"] else "unreachable",
            "languages": st.get("languages", {}),
            "message": None if st["available"] else "The code runner is temporarily unreachable."}


@router.post("/run", dependencies=[Depends(rate_limit("sandbox", "rate_limit_sandbox_per_minute"))])
def run(body: RunIn, user: User = CurrentUser, db: Session = DB) -> dict:
    client = get_sandbox()
    if client is None:
        raise AppError("Secure code execution is not configured on this server.", code="sandbox_disabled", status_code=503)
    plan = plan_for(db, user)
    limit = entitlement_limit(db, plan, "sandbox_runs_per_day")
    if limit is not None:
        since = datetime.now(UTC) - timedelta(days=1)
        used = db.scalar(select(func.count()).select_from(UsageEvent).where(
            UsageEvent.user_id == user.id, UsageEvent.event_type == "sandbox_run", UsageEvent.created_at >= since)) or 0
        if used >= limit:
            raise AppError(f"Daily code-run limit reached for the {plan} plan ({limit}/day).", code="quota_exceeded", status_code=429)
    payload = {"language": body.language, "code": body.code, "stdin": body.stdin, "timeout_ms": 5000}
    if body.language == "sql":
        payload["sql_setup"] = body.sql_setup or ""
    result = client.run(payload)
    track(db, user.id, "sandbox_run", language=body.language, status=result.get("status"))
    db.commit()
    return {"mode": "sandbox", **{k: result.get(k) for k in ("status", "stdout", "stderr", "exit_code", "duration_ms",
                                                                "timed_out", "truncated", "sql", "tests")}}
