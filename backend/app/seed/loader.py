"""Idempotent seed loader.

Loads roles, plans/entitlements, achievements, the curriculum (tracks > courses > modules > lessons with versioned
content, quizzes and exercises), standalone challenges, the 100-entry agent catalog (with source files, example
runs and evaluation reports for the ten reference implementations), projects, announcements and development accounts.

Re-running is safe: rows are matched by slug and updated in place. Lesson and agent content changes create a new
published version instead of mutating history.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import (
    Achievement,
    Agent,
    AgentFile,
    AgentVersion,
    Announcement,
    Assessment,
    Course,
    Entitlement,
    Exercise,
    LearningTrack,
    Lesson,
    LessonVersion,
    Module,
    Project,
    PromptTemplate,
    PromptTestCase,
    PromptVersion,
    Question,
    RagDataset,
    RagDocument,
    RagQuestion,
    Role,
    User,
)
from ..services.templating import variables as template_variables

log = logging.getLogger("agentforge.seed")
CONTENT = Path(__file__).parent / "content"
ROLES = {"learner": "Learner", "author": "Content author", "reviewer": "Content reviewer", "admin": "Administrator"}


def _yaml(name: str) -> Any:
    return yaml.safe_load((CONTENT / name).read_text(encoding="utf-8"))


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _upsert(db: Session, model, where: dict, values: dict):
    row = db.scalar(select(model).filter_by(**where))
    if row is None:
        row = model(**where, **values)
        db.add(row)
    else:
        for k, v in values.items():
            setattr(row, k, v)
    db.flush()
    return row


# ------------------------------------------------------------------ platform

def seed_roles(db: Session) -> None:
    for name, desc in ROLES.items():
        _upsert(db, Role, {"name": name}, {"description": desc})


def seed_platform(db: Session) -> None:
    data = _yaml("platform.yaml")
    for plan, features in data["entitlements"].items():
        for key, cfg in features.items():
            _upsert(db, Entitlement, {"plan": plan, "feature_key": key},
                    {"enabled": cfg.get("enabled", True), "limit_value": cfg.get("limit")})
    for a in data["achievements"]:
        _upsert(db, Achievement, {"slug": a["slug"]},
                {"name": a["name"], "description": a["description"], "icon": a["icon"], "criteria": a["criteria"]})
    for p in data["projects"]:
        _upsert(db, Project, {"slug": p["slug"]},
                {"title": p["title"], "summary": p["summary"], "difficulty": p["difficulty"], "track_slug": p.get("track"),
                 "skills": p["skills"], "requirements": p["requirements"], "estimated_hours": p["hours"],
                 "tier": p.get("tier", "free"), "status": "published"})
    for a in data.get("announcements", []):
        if not db.scalar(select(Announcement).where(Announcement.title == a["title"])):
            db.add(Announcement(title=a["title"], body_md=a["body_md"], status="published", published_at=datetime.now(UTC)))


# ------------------------------------------------------------------ exercises

def exercise_spec(ex: dict) -> dict:
    kind = ex.get("kind", "code")
    if kind == "code":
        return {"sql": ex["sql"]} if ex.get("language") == "sql" else {"tests": ex["tests"]}
    if kind == "multiple_choice":
        return {"options": ex["options"], "correct_index": ex["correct_index"]}
    return {"rubric": ex["rubric"], "min_words": ex.get("min_words", 50)}


def upsert_exercise(db: Session, ex: dict, lesson_id=None) -> Exercise:
    return _upsert(db, Exercise, {"slug": ex["slug"]}, {
        "title": ex["title"], "lesson_id": lesson_id, "kind": ex.get("kind", "code"), "category": ex["category"],
        "difficulty": ex["difficulty"], "language": ex.get("language"), "prompt_md": ex["prompt_md"],
        "starter_code": ex.get("starter_code", ""), "spec": exercise_spec(ex), "hints": ex.get("hints", []),
        "explanation_md": ex.get("explanation_md", ""), "solution": ex.get("solution", ""), "points": ex.get("points", 10),
        "time_limit_minutes": ex.get("time_limit_minutes"),
        "is_daily_eligible": ex.get("daily", ex.get("kind", "code") != "manual_review"),
        "is_weekly_project": ex.get("is_weekly_project", False), "tier": ex.get("tier", "free"),
        "status": "published", "tags": ex.get("tags", []),
    })


# ------------------------------------------------------------------ curriculum

def _publish_lesson_content(db: Session, lesson: Lesson, content: dict) -> None:
    latest = db.scalar(select(LessonVersion).where(LessonVersion.lesson_id == lesson.id)
                       .order_by(LessonVersion.version.desc()).limit(1))
    if latest is not None and _digest(latest.content) == _digest(content):
        if lesson.published_version_id is None:
            latest.status, latest.published_at = "published", latest.published_at or datetime.now(UTC)
            lesson.published_version_id = latest.id
        return
    if lesson.published_version is not None:
        lesson.published_version.status = "archived"
    v = LessonVersion(lesson_id=lesson.id, version=(latest.version + 1) if latest else 1, status="published",
                      content=content, change_note="Seeded from repository content", published_at=datetime.now(UTC))
    db.add(v)
    db.flush()
    lesson.published_version_id = v.id


def _seed_quiz(db: Session, lesson: Lesson, quiz: list[dict]) -> None:
    a = _upsert(db, Assessment, {"slug": f"{lesson.slug}-quiz"},
                {"title": f"{lesson.title} - check your understanding", "lesson_id": lesson.id, "pass_threshold": 0.7})
    existing = db.scalars(select(Question).where(Question.assessment_id == a.id)).all()
    for q in existing:
        db.delete(q)
    db.flush()
    for i, q in enumerate(quiz):
        db.add(Question(assessment_id=a.id, kind="mcq", difficulty="beginner", prompt_md=q["prompt"], options=q["options"],
                        answer={"index": q["answer"]}, explanation_md=q.get("explanation", ""), order_index=i))


def seed_curriculum(db: Session) -> dict[str, int]:
    data = _yaml("curriculum.yaml")
    stats = {"tracks": 0, "lessons": 0, "published_lessons": 0, "exercises": 0}
    for ti, t in enumerate(data["tracks"]):
        track = _upsert(db, LearningTrack, {"slug": t["slug"]}, {
            "title": t["title"], "summary": t["summary"], "description": t.get("description", t["summary"]),
            "icon": t.get("icon", "book"), "color": t.get("color", "indigo"), "level": t.get("level", "beginner"),
            "order_index": ti, "tier": t.get("tier", "free"), "status": "published", "tags": t.get("tags", []),
            "outcomes": t.get("outcomes", []),
        })
        stats["tracks"] += 1
        for ci, c in enumerate(t["courses"]):
            course = _upsert(db, Course, {"track_id": track.id, "slug": c["slug"]}, {
                "title": c["title"], "summary": c.get("summary", ""), "level": c.get("level", "beginner"),
                "order_index": ci, "estimated_hours": c.get("hours", 1), "tier": c.get("tier", "free"), "status": "published",
            })
            for mi, m in enumerate(c["modules"]):
                module = _upsert(db, Module, {"course_id": course.id, "slug": m["slug"]},
                                 {"title": m["title"], "summary": m.get("summary", ""), "order_index": mi})
                for li, outline in enumerate(m["lessons"]):
                    stats["lessons"] += 1
                    path = CONTENT / "lessons" / f"{outline['slug']}.yaml"
                    doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
                    lesson = _upsert(db, Lesson, {"slug": outline["slug"]}, {
                        "module_id": module.id, "title": (doc or outline)["title"],
                        "summary": (doc or {}).get("summary", ""), "order_index": li,
                        "estimated_minutes": (doc or {}).get("minutes", 15), "level": (doc or {}).get("level", c.get("level", "beginner")),
                        "tier": (doc or outline).get("tier", outline.get("tier", "free")),
                        "status": "published" if doc else "draft",
                        "prerequisites": (doc or {}).get("prerequisites", []), "tags": (doc or {}).get("tags", []),
                    })
                    if doc is None:
                        continue
                    stats["published_lessons"] += 1
                    _publish_lesson_content(db, lesson, {"sections": doc["sections"]})
                    _seed_quiz(db, lesson, doc.get("quiz", []))
                    for ex in doc.get("exercises", []):
                        upsert_exercise(db, ex, lesson.id)
                        stats["exercises"] += 1
    return stats


def seed_challenges(db: Session) -> int:
    items = _yaml("challenges.yaml")["challenges"]
    for ex in items:
        upsert_exercise(db, ex)
    return len(items)


# ------------------------------------------------------------------ agents

def _language(path: str) -> str:
    return {"py": "python", "jsonl": "json", "md": "markdown", "json": "json"}.get(path.rsplit(".", 1)[-1], "text")


def seed_agents(db: Session, with_runs: bool = True) -> dict[str, int]:
    """Catalog entries + versioned blueprints. Implemented agents also get source files, example runs and evals."""
    from agentforge_agents.catalog import all_entries
    from agentforge_agents.core import MockProvider, run_agent
    from agentforge_agents.evals import run_eval
    from agentforge_agents.registry import get_spec, source_files

    from ..services.sandbox import get_sandbox

    sandbox = get_sandbox()
    sandbox_run = sandbox.run if sandbox else None
    stats = {"agents": 0, "implemented": 0, "versions_created": 0}
    for e in all_entries():
        impl = bool(e.get("has_reference_impl"))
        agent = _upsert(db, Agent, {"slug": e["slug"]}, {
            "number": e["number"], "name": e["name"], "category": e["category"], "level": e["level"],
            "build_hours": e["build_hours"], "summary": e["summary"], "verdict": e["verdict"], "has_reference_impl": impl,
            "tier": "pro" if e["level"] == "expert" and not impl else "free", "status": "published", "tags": e.get("tags", []),
        })
        stats["agents"] += 1
        spec = get_spec(e["slug"]) if impl else None
        files = source_files(spec) if spec else []
        fingerprint = _digest({"blueprint": e, "files": [(f["path"], f["content"]) for f in files]})
        current = agent.current_version
        if current is not None and (current.blueprint or {}).get("_fingerprint") == fingerprint:
            stats["implemented"] += impl
            continue
        example_runs: list[dict] = []
        eval_report = None
        if spec and with_runs:
            for i, example in enumerate(spec.examples):
                r = run_agent(spec, example, provider=MockProvider(), sandbox=sandbox_run)
                example_runs.append({"index": i, "label": example.get("_label") or f"Example {i + 1}", **r.to_dict(), "input": example})
            eval_report = run_eval(spec, provider=MockProvider(), sandbox=sandbox_run)
            eval_report["provider"] = "mock"
            eval_report["sandbox"] = bool(sandbox_run)
            eval_report["generated_at"] = datetime.now(UTC).isoformat()
        latest = max((v.version for v in db.scalars(select(AgentVersion).where(AgentVersion.agent_id == agent.id))), default=0)
        if current is not None:
            current.status = "archived"
        v = AgentVersion(agent_id=agent.id, version=latest + 1, blueprint={**e, "_fingerprint": fingerprint},
                         example_runs=json.loads(json.dumps(example_runs, default=str)),
                         eval_report=json.loads(json.dumps(eval_report, default=str)) if eval_report else None, status="published")
        db.add(v)
        db.flush()
        for f in files:
            db.add(AgentFile(agent_version_id=v.id, path=f["path"], language=f.get("language") or _language(f["path"]), content=f["content"]))
        agent.current_version_id = v.id
        stats["versions_created"] += 1
        stats["implemented"] += impl
        db.flush()
    return stats


# ------------------------------------------------------------------ prompt lab

def seed_prompts(db: Session) -> int:
    data = _yaml("prompts.yaml")
    for t in data["templates"]:
        tpl = _upsert(db, PromptTemplate, {"slug": t["slug"]}, {"name": t["name"], "category": t["category"],
                                                                 "description": t.get("description", ""), "owner_id": None, "status": "published"})
        existing = {v.version: v for v in db.scalars(select(PromptVersion).where(PromptVersion.template_id == tpl.id)).all()}
        for i, v in enumerate(t["versions"], start=1):
            values = {"system": v.get("system", ""), "user_template": v["user_template"], "params": v.get("params", {}),
                      "variables": template_variables(v.get("system", "") + "\n" + v["user_template"]), "change_note": v.get("change_note", "")}
            if i in existing:
                for k, val in values.items():
                    setattr(existing[i], k, val)
            else:
                existing[i] = PromptVersion(template_id=tpl.id, version=i, **values)
                db.add(existing[i])
        db.flush()
        tpl.current_version_id = existing[len(t["versions"])].id
        for c in db.scalars(select(PromptTestCase).where(PromptTestCase.template_id == tpl.id)).all():
            db.delete(c)
        db.flush()
        for i, c in enumerate(t.get("test_cases", [])):
            db.add(PromptTestCase(template_id=tpl.id, name=c["name"], variables=c.get("variables", {}),
                                  assertions=c.get("assertions", []), order_index=i))
    return len(data["templates"])


# ------------------------------------------------------------------ RAG lab

def _front_matter(raw: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    if raw.startswith("---"):
        head, _, body = raw[3:].partition("\n---")
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        return meta, body.lstrip("\n")
    return meta, raw


def seed_rag(db: Session) -> dict[str, int]:
    from ..services.rag.retrieval import clean_text

    ds = _upsert(db, RagDataset, {"slug": "northwind-handbook"}, {
        "name": "Northwind Cloud handbook (demo)", "is_public": True, "owner_id": None,
        "description": "Policies, runbooks and FAQs of a fictional SaaS company. Some documents are restricted to engineering or HR, "
                       "and one imported page contains a prompt-injection attempt."})
    keep: set[str] = set()
    for path in sorted((CONTENT / "rag" / "northwind").glob("*.md")):
        meta, body = _front_matter(path.read_text(encoding="utf-8"))
        text = clean_text(body)
        h = hashlib.sha256(text.encode()).hexdigest()
        groups = [g.strip() for g in meta.get("allowed_groups", "everyone").split(",") if g.strip()]
        doc = db.scalar(select(RagDocument).where(RagDocument.dataset_id == ds.id, RagDocument.source == path.stem))
        if doc is None:
            db.add(RagDocument(dataset_id=ds.id, title=meta.get("title", path.stem), source=path.stem, mime="text/markdown",
                               text=text, content_hash=h, allowed_groups=groups))
        else:
            doc.title, doc.text, doc.content_hash, doc.allowed_groups = meta.get("title", path.stem), text, h, groups
        keep.add(path.stem)
    for doc in db.scalars(select(RagDocument).where(RagDocument.dataset_id == ds.id)).all():
        if doc.source not in keep:
            db.delete(doc)
    for q in db.scalars(select(RagQuestion).where(RagQuestion.dataset_id == ds.id)).all():
        db.delete(q)
    questions = _yaml("rag/questions.yaml")["northwind-handbook"]
    for q in questions:
        db.add(RagQuestion(dataset_id=ds.id, question=q["question"], relevant_sources=q.get("relevant_sources", []),
                           answer_contains=q.get("answer_contains", []), user_groups=q.get("user_groups", ["everyone"])))
    db.flush()
    return {"documents": len(keep), "questions": len(questions)}


# ------------------------------------------------------------------ interview arena & mentor corpus

def seed_interviews(db: Session) -> int:
    tracks = _yaml("interviews.yaml")["tracks"]
    n = 0
    for slug, t in tracks.items():
        for i, q in enumerate(t["questions"]):
            values = {"kind": "open", "difficulty": q["difficulty"], "prompt_md": q["prompt"], "concise_answer": q["concise"],
                      "explanation_md": q["explanation"], "follow_ups": q.get("follow_ups", []), "common_mistakes": q.get("mistakes", []),
                      "answer": {"example": q.get("example", ""), "key_points": q["key_points"]}, "options": []}
            _upsert(db, Question, {"interview_track": slug, "order_index": i, "assessment_id": None}, values)
            n += 1
    return n


LESSON_PARTS = [("explanation", "The idea"), ("why_it_matters", "Why it matters"), ("mental_model", "Mental model"),
                ("real_world", "In the real world"), ("debugging", "Debugging"), ("performance_security", "Performance and security")]


def seed_course_corpus(db: Session) -> int:
    """Index published lessons as a RAG dataset so the AI mentor can ground answers and cite lessons."""
    ds = _upsert(db, RagDataset, {"slug": "course-content"}, {
        "name": "AgentForge lessons", "owner_id": None, "is_public": True,
        "description": "The published lessons of this academy. The AI mentor retrieves from it to ground and cite its answers."})
    lessons = db.scalars(select(Lesson).where(Lesson.status == "published")).all()
    keep = set()
    for lesson in lessons:
        if lesson.published_version is None:
            continue
        s = lesson.published_version.content.get("sections", {})
        parts = [f"# {lesson.title}", lesson.summary]
        for key, heading in LESSON_PARTS:
            if s.get(key):
                parts.append(f"## {heading}\n{s[key]}")
        if s.get("common_mistakes"):
            parts.append("## Common mistakes\n" + "\n".join(f"- {m['mistake']} Fix: {m['fix']}" for m in s["common_mistakes"]))
        text = "\n\n".join(parts)
        h = hashlib.sha256(text.encode()).hexdigest()
        doc = db.scalar(select(RagDocument).where(RagDocument.dataset_id == ds.id, RagDocument.source == lesson.slug))
        if doc is None:
            db.add(RagDocument(dataset_id=ds.id, title=lesson.title, source=lesson.slug, mime="text/markdown", text=text,
                               content_hash=h, allowed_groups=["everyone"]))
        elif doc.content_hash != h:
            doc.title, doc.text, doc.content_hash = lesson.title, text, h
        keep.add(lesson.slug)
    for doc in db.scalars(select(RagDocument).where(RagDocument.dataset_id == ds.id)).all():
        if doc.source not in keep:
            db.delete(doc)
    db.flush()
    return len(keep)


# ------------------------------------------------------------------ accounts

def seed_users(db: Session) -> list[str]:
    """Development accounts. In production they are created only if SEED_ADMIN_PASSWORD was changed (config guard)."""
    from ..modules.auth import create_user

    s = get_settings()
    accounts = [
        (s.seed_admin_email, s.seed_admin_password, "Ada Admin", ("admin", "author", "reviewer", "learner"), "team"),
        (s.seed_demo_email, s.seed_demo_password, "Lee Learner", ("learner",), "free"),
    ]
    if s.env != "production":
        accounts.append(("author@example.com", s.seed_demo_password, "Ari Author", ("author", "learner"), "pro"))
    created = []
    for email, password, name, roles, plan in accounts:
        if db.scalar(select(User.id).where(User.email == email.lower())):
            continue
        create_user(db, email, password, name, roles=roles, plan=plan, verified=True)
        created.append(email)
    return created


def seed_all(db: Session, with_users: bool = True, with_agent_runs: bool = True) -> dict[str, Any]:
    seed_roles(db)
    seed_platform(db)
    out: dict[str, Any] = {"curriculum": seed_curriculum(db), "challenges": seed_challenges(db),
                           "agents": seed_agents(db, with_runs=with_agent_runs), "prompts": seed_prompts(db), "rag": seed_rag(db),
                           "interview_questions": seed_interviews(db)}
    out["course_corpus"] = seed_course_corpus(db)
    if with_users:
        out["users_created"] = seed_users(db)
    db.commit()
    return out
