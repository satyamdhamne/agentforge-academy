"""Challenge engine: listing, daily challenge, hints, graded attempts (sandboxed code, MCQ, manual review)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..api.deps import DB, CurrentUser, OptionalUser, rate_limit
from ..core.errors import AppError, Conflict, NotFound
from ..core.ratelimit import limiter
from ..models import ChallengeAttempt, Exercise, HintReveal, User
from ..services import achievements as ach
from ..services.common import can_access_tier, plan_for, track
from ..services.sandbox import SandboxUnavailable, get_sandbox

router = APIRouter(prefix="/challenges", tags=["challenges"])

HINT_PENALTY = 0.2          # each revealed hint reduces points by 20%...
MIN_POINT_FACTOR = 0.4      # ...down to a floor of 40%
ATTEMPT_COOLDOWN_S = 3      # minimum seconds between graded attempts on the same challenge


# ------------------------------------------------------------------ presentation helpers

def exercise_card(e: Exercise) -> dict:
    return {"slug": e.slug, "title": e.title, "kind": e.kind, "category": e.category, "difficulty": e.difficulty,
            "language": e.language, "points": e.points, "tier": e.tier, "tags": e.tags,
            "time_limit_minutes": e.time_limit_minutes, "is_weekly_project": e.is_weekly_project}


def _public_tests(e: Exercise) -> list[dict]:
    tests = (e.spec or {}).get("tests") or {}
    return [{"args": c["args"], "expected": c.get("expected")} for c in tests.get("cases", []) if not c.get("hidden")]


def _hidden_count(e: Exercise) -> int:
    return sum(1 for c in ((e.spec or {}).get("tests") or {}).get("cases", []) if c.get("hidden"))


def daily_challenge(db: Session, day: datetime | None = None) -> Exercise | None:
    """Deterministic per UTC day so every learner gets the same daily challenge."""
    eligible = db.scalars(select(Exercise).where(Exercise.is_daily_eligible.is_(True), Exercise.status == "published",
                                                 Exercise.tier == "free").order_by(Exercise.slug)).all()
    if not eligible:
        return None
    key = (day or datetime.now(UTC)).date().isoformat()
    return eligible[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(eligible)]


def _get(db: Session, slug: str) -> Exercise:
    e = db.scalar(select(Exercise).where(Exercise.slug == slug, Exercise.status == "published"))
    if e is None:
        raise NotFound("Challenge not found")
    return e


def _user_state(db: Session, user: User | None, e: Exercise) -> dict:
    if user is None:
        return {"attempts": 0, "solved": False, "points_earned": 0, "hints_revealed": []}
    attempts = db.scalars(select(ChallengeAttempt).where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.exercise_id == e.id)
                          .order_by(ChallengeAttempt.created_at)).all()
    revealed = sorted(db.scalars(select(HintReveal.hint_index).where(HintReveal.user_id == user.id, HintReveal.exercise_id == e.id)).all())
    return {"attempts": len(attempts), "solved": any(a.status in ("passed", "reviewed") and a.score >= 0.7 for a in attempts),
            "points_earned": sum(a.points_awarded for a in attempts), "hints_revealed": revealed,
            "pending_review": any(a.status == "pending_review" for a in attempts)}


# ------------------------------------------------------------------ listing & detail

@router.get("")
def list_challenges(
    difficulty: str | None = Query(None, pattern="^(beginner|intermediate|advanced|expert)$"),
    category: str | None = Query(None, max_length=30),
    kind: str | None = Query(None, pattern="^(code|multiple_choice|manual_review)$"),
    q: str | None = Query(None, max_length=100),
    weekly: bool | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    user: User | None = OptionalUser, db: Session = DB,
) -> dict:
    stmt = select(Exercise).where(Exercise.status == "published", Exercise.lesson_id.is_(None))
    if difficulty:
        stmt = stmt.where(Exercise.difficulty == difficulty)
    if category:
        stmt = stmt.where(Exercise.category == category)
    if kind:
        stmt = stmt.where(Exercise.kind == kind)
    if weekly is not None:
        stmt = stmt.where(Exercise.is_weekly_project.is_(weekly))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Exercise.title).like(like), func.lower(Exercise.prompt_md).like(like)))
    order = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}
    items = sorted(db.scalars(stmt).all(), key=lambda e: (order[e.difficulty], e.title))
    total = len(items)
    page_items = items[(page - 1) * page_size: page * page_size]
    solved: set = set()
    if user:
        solved = set(db.scalars(select(ChallengeAttempt.exercise_id).where(
            ChallengeAttempt.user_id == user.id, ChallengeAttempt.points_awarded > 0)).all())
    plan = plan_for(db, user)
    categories = sorted(set(db.scalars(select(Exercise.category).where(Exercise.status == "published")).all()))
    return {"items": [{**exercise_card(e), "solved": e.id in solved, "locked": not can_access_tier(plan, e.tier)} for e in page_items],
            "total": total, "page": page, "page_size": page_size, "categories": categories}


@router.get("/daily")
def get_daily(user: User | None = OptionalUser, db: Session = DB) -> dict:
    e = daily_challenge(db)
    if e is None:
        raise NotFound("No daily challenge available")
    return {**exercise_card(e), "date": datetime.now(UTC).date().isoformat(), **_user_state(db, user, e)}


@router.get("/{slug}")
def get_challenge(slug: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    e = _get(db, slug)
    plan = plan_for(db, user)
    if not can_access_tier(plan, e.tier):
        return {**exercise_card(e), "locked": True, "required_tier": e.tier}
    state = _user_state(db, user, e)
    spec = e.spec or {}
    detail: dict[str, Any] = {
        **exercise_card(e), "locked": False, "prompt_md": e.prompt_md, "starter_code": e.starter_code,
        "hints_total": len(e.hints), "hints": [{"index": i, "text": e.hints[i]} for i in state["hints_revealed"] if i < len(e.hints)],
        "public_tests": _public_tests(e), "hidden_tests": _hidden_count(e),
        "options": spec.get("options") if e.kind == "multiple_choice" else None,
        "rubric": spec.get("rubric") if e.kind == "manual_review" else None,
        "min_words": spec.get("min_words"),
        "sql_setup": (spec.get("sql") or {}).get("setup") if e.language == "sql" else None,
        "execution": "sandbox" if e.kind == "code" and get_sandbox() is not None else ("unavailable" if e.kind == "code" else "none"),
        **state,
    }
    if state["solved"]:  # explanations and reference solutions unlock after solving - not before
        detail["explanation_md"] = e.explanation_md
        detail["solution"] = e.solution
    return detail


@router.post("/{slug}/hints/{index}")
def reveal_hint(slug: str, index: int, user: User = CurrentUser, db: Session = DB) -> dict:
    e = _get(db, slug)
    if index < 0 or index >= len(e.hints):
        raise NotFound("Hint not found")
    revealed = set(db.scalars(select(HintReveal.hint_index).where(HintReveal.user_id == user.id, HintReveal.exercise_id == e.id)).all())
    if index > 0 and (index - 1) not in revealed:
        raise AppError("Reveal hints in order.", code="hint_order")
    if index not in revealed:
        db.add(HintReveal(user_id=user.id, exercise_id=e.id, hint_index=index))
        track(db, user.id, "hint_revealed", exercise=e.slug)
        db.commit()
        revealed.add(index)
    factor = max(MIN_POINT_FACTOR, 1 - HINT_PENALTY * len(revealed))
    return {"index": index, "text": e.hints[index], "points_available": int(round(e.points * factor))}


# ------------------------------------------------------------------ grading

class AttemptIn(BaseModel):
    code: str | None = Field(None, max_length=50_000)
    selected_index: int | None = Field(None, ge=0, le=20)
    answer_text: str | None = Field(None, max_length=20_000)


def _submission(e: Exercise, body: AttemptIn) -> dict:
    if e.kind == "code":
        if not body.code or not body.code.strip():
            raise AppError("Submit some code.", code="empty_submission", status_code=422)
        return {"code": body.code}
    if e.kind == "multiple_choice":
        if body.selected_index is None:
            raise AppError("Choose an option.", code="empty_submission", status_code=422)
        return {"selected_index": body.selected_index}
    text = (body.answer_text or "").strip()
    min_words = (e.spec or {}).get("min_words", 50)
    if len(text.split()) < min_words:
        raise AppError(f"Write at least {min_words} words so a reviewer can assess your reasoning.", code="too_short", status_code=422)
    return {"answer_text": text}


def grade(e: Exercise, submission: dict) -> tuple[str, float, dict, str]:
    """Returns (status, score 0..1, result, execution_mode)."""
    spec = e.spec or {}
    if e.kind == "multiple_choice":
        correct = submission["selected_index"] == spec.get("correct_index")
        return ("passed" if correct else "failed", 1.0 if correct else 0.0, {"correct": correct}, "none")
    if e.kind == "manual_review":
        return ("pending_review", 0.0, {"message": "Submitted for review against the published rubric."}, "none")

    client = get_sandbox()
    if client is None:
        return ("not_graded", 0.0, {"message": "Secure code execution is not configured on this server, so this submission "
                                                "was saved but not graded. No points are awarded for ungraded work."}, "unavailable")
    payload: dict[str, Any] = {"language": e.language, "code": submission["code"], "timeout_ms": 5000}
    if e.language == "sql":
        sql = spec["sql"]
        payload["sql_setup"] = sql.get("setup", "")
        payload["sql_expected"] = {k: sql[k] for k in ("expected_rows", "expected_columns", "ordered") if k in sql}
    else:
        tests = spec["tests"]
        payload["tests"] = {"function": tests["function"], "compare": tests.get("compare", "exact"),
                            "cases": [{"args": c["args"], "expected": c.get("expected")} for c in tests["cases"]]}
    try:
        raw = client.run(payload)
    except SandboxUnavailable as exc:
        return ("not_graded", 0.0, {"message": exc.message}, "unavailable")
    t = raw.get("tests") or {}
    cases = ((spec.get("tests") or {}).get("cases")) or [{}]
    results = []
    for r in t.get("results", []):
        hidden = bool(cases[r["index"]].get("hidden")) if r["index"] < len(cases) else False
        item = {"index": r["index"], "passed": bool(r.get("passed")), "hidden": hidden}
        if not hidden:  # never reveal hidden test inputs/outputs
            item.update({k: r.get(k) for k in ("actual", "error") if k in r})
            if e.language != "sql":
                item["args"] = cases[r["index"]].get("args")
                item["expected"] = cases[r["index"]].get("expected")
        elif r.get("error"):
            item["error"] = r["error"].split(":")[0]
        results.append(item)
    total = t.get("total") or 0
    passed = t.get("passed") or 0
    score = passed / total if total else 0.0
    status = "passed" if total and passed == total and not t.get("compile_error") else ("error" if t.get("compile_error") or raw.get("timed_out") else "failed")
    result = {"tests_passed": passed, "tests_total": total, "results": results, "compile_error": t.get("compile_error"),
              "stdout": (raw.get("stdout") or "")[-4000:], "stderr": (raw.get("stderr") or "")[-2000:],
              "timed_out": raw.get("timed_out", False), "duration_ms": raw.get("duration_ms")}
    if e.language == "sql" and raw.get("sql"):
        result["sql"] = {"columns": raw["sql"].get("columns", []), "rows": raw["sql"].get("rows", [])[:50]}
    return status, round(score, 3), result, "sandbox"


def points_for(e: Exercise, status: str, score: float, hints_used: int, prior_attempts: list[ChallengeAttempt]) -> int:
    """Points only on the FIRST successful attempt; hints and (for MCQ) wrong guesses reduce them."""
    if any(a.points_awarded > 0 for a in prior_attempts):
        return 0
    factor = max(MIN_POINT_FACTOR, 1 - HINT_PENALTY * hints_used)
    if e.kind == "multiple_choice":
        if status != "passed":
            return 0
        wrong = sum(1 for a in prior_attempts if a.status == "failed")
        return int(round(e.points * factor / (wrong + 1)))  # guessing through options earns little
    if e.kind == "code":
        return int(round(e.points * factor)) if status == "passed" else 0
    return int(round(e.points * factor * score))  # manual review: scaled by rubric score


def attempt_out(a: ChallengeAttempt) -> dict:
    return {"id": str(a.id), "status": a.status, "score": a.score, "points_awarded": a.points_awarded, "hints_used": a.hints_used,
            "execution_mode": a.execution_mode, "result": a.result, "review_feedback": a.review_feedback,
            "created_at": a.created_at, "reviewed_at": a.reviewed_at}


@router.post("/{slug}/attempts", status_code=201, dependencies=[Depends(rate_limit("attempts", "rate_limit_sandbox_per_minute"))])
def submit_attempt(slug: str, body: AttemptIn, request: Request, user: User = CurrentUser, db: Session = DB,
                   idempotency_key: str | None = Header(None, max_length=100)) -> dict:
    e = _get(db, slug)
    if not can_access_tier(plan_for(db, user), e.tier):
        raise AppError("Upgrade required for this challenge.", code="upgrade_required", status_code=402)
    if idempotency_key:
        existing = db.scalar(select(ChallengeAttempt).where(ChallengeAttempt.user_id == user.id,
                                                            ChallengeAttempt.idempotency_key == idempotency_key))
        if existing:
            if existing.exercise_id != e.id:
                raise Conflict("Idempotency key was already used for a different challenge.")
            return {**attempt_out(existing), "duplicate": True, "new_achievements": []}

    submission = _submission(e, body)
    sub_hash = hashlib.sha256(json.dumps(submission, sort_keys=True).encode()).hexdigest()
    prior = db.scalars(select(ChallengeAttempt).where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.exercise_id == e.id)
                       .order_by(ChallengeAttempt.created_at)).all()
    same = next((a for a in reversed(prior) if a.submission_hash == sub_hash and a.status != "not_graded"), None)
    if same:  # identical resubmission: return the earlier verdict instead of re-grading or re-counting
        return {**attempt_out(same), "duplicate": True, "new_achievements": []}
    if prior:
        last = prior[-1].created_at if prior[-1].created_at.tzinfo else prior[-1].created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - last < timedelta(seconds=ATTEMPT_COOLDOWN_S):
            raise AppError("Slow down - wait a few seconds between attempts.", code="cooldown", status_code=429)
    if e.kind == "manual_review" and any(a.status == "pending_review" for a in prior):
        raise Conflict("You already have a submission waiting for review.")
    limiter.hit(f"attempt:{user.id}:{e.id}", 20, 3600)  # hard cap per challenge per hour

    status, score, result, mode = grade(e, submission)
    hints_used = db.scalar(select(func.count()).select_from(HintReveal).where(HintReveal.user_id == user.id, HintReveal.exercise_id == e.id)) or 0
    points = points_for(e, status, score, hints_used, prior) if status != "pending_review" else 0
    attempt = ChallengeAttempt(user_id=user.id, exercise_id=e.id, submission=submission, submission_hash=sub_hash,
                               idempotency_key=idempotency_key, status=status, score=score, points_awarded=points,
                               hints_used=hints_used, execution_mode=mode, result=result)
    db.add(attempt)
    track(db, user.id, "challenge_attempted", exercise=e.slug, status=status, points=points, mode=mode, difficulty=e.difficulty)
    db.flush()
    new_badges = ach.evaluate(db, user) if points else []
    db.commit()
    out = attempt_out(attempt)
    if status == "passed":
        out["explanation_md"] = e.explanation_md
        out["solution"] = e.solution
    out["new_achievements"] = [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in new_badges]
    return out


@router.get("/{slug}/attempts")
def list_attempts(slug: str, user: User = CurrentUser, db: Session = DB) -> dict:
    e = _get(db, slug)
    rows = db.scalars(select(ChallengeAttempt).where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.exercise_id == e.id)
                      .order_by(ChallengeAttempt.created_at.desc()).limit(50)).all()
    return {"items": [attempt_out(a) for a in rows]}
