"""RAG Engineering Lab: datasets, uploads with document permissions, chunk previews, queries and evaluation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..api.deps import DB, CurrentUser, OptionalUser, rate_limit
from ..core.errors import AppError, Forbidden, NotFound
from ..models import Evaluation, EvaluationCase, RagDataset, RagDocument, RagIndex, RagQuestion, User
from ..services.common import audit, plan_for, track
from ..services.llm import enforce_quota, groups_for, provider_for
from ..services.rag import embeddings
from ..services.rag.chunking import STRATEGIES, chunk
from ..services.rag.pipeline import DEFAULT_SYSTEM, DEFAULT_USER, evaluate, query
from ..services.rag.retrieval import clean_text, normalize_config

router = APIRouter(prefix="/rag", tags=["rag lab"])
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DOCS_PER_DATASET = 50


def _visible(user: User | None):
    cond = or_(RagDataset.is_public.is_(True), RagDataset.owner_id.is_(None))
    if user is None:
        return cond
    conds = [cond, RagDataset.owner_id == user.id]
    if user.organization_id:
        conds.append(RagDataset.organization_id == user.organization_id)
    return or_(*conds)


def _dataset(db: Session, key: str, user: User | None) -> RagDataset:
    try:
        stmt = select(RagDataset).where(RagDataset.id == uuid.UUID(key))
    except ValueError:
        stmt = select(RagDataset).where(RagDataset.slug == key)
    ds = db.scalar(stmt.where(_visible(user)))
    if ds is None:
        raise NotFound("Dataset not found")
    return ds


def _owned(db: Session, key: str, user: User) -> RagDataset:
    ds = _dataset(db, key, user)
    if ds.owner_id != user.id:
        raise Forbidden("Only the dataset owner can change it. Create your own dataset to upload documents.")
    return ds


@router.get("/options")
def options(user: User | None = OptionalUser, db: Session = DB) -> dict:
    live = plan_for(db, user) != "free"
    return {"chunkers": [{"key": "fixed", "label": "Fixed windows", "note": "Every N words, ignores structure."},
                         {"key": "recursive", "label": "Recursive", "note": "Paragraphs, then sentences, packed up to N words."},
                         {"key": "markdown", "label": "Structure-aware", "note": "Splits on headings and keeps the heading path."}],
            "strategies": [{"key": "vector", "label": "Vector"}, {"key": "keyword", "label": "Keyword (BM25)"},
                           {"key": "hybrid", "label": "Hybrid (RRF)"}],
            "embedders": embeddings.available(live), "defaults": normalize_config(None),
            "default_prompt": {"system": DEFAULT_SYSTEM, "user": DEFAULT_USER}, "your_groups": groups_for(user)}


@router.get("/datasets")
def list_datasets(user: User | None = OptionalUser, db: Session = DB) -> dict:
    rows = db.scalars(select(RagDataset).where(_visible(user)).order_by(RagDataset.owner_id.is_(None).desc(), RagDataset.name)).all()
    counts = dict(db.execute(select(RagDocument.dataset_id, func.count()).group_by(RagDocument.dataset_id)).all())
    qs = dict(db.execute(select(RagQuestion.dataset_id, func.count()).group_by(RagQuestion.dataset_id)).all())
    return {"items": [{"id": str(d.id), "slug": d.slug, "name": d.name, "description": d.description,
                       "mine": user is not None and d.owner_id == user.id, "documents": counts.get(d.id, 0),
                       "questions": qs.get(d.id, 0)} for d in rows]}


class DatasetIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: str = Field("", max_length=2000)


@router.post("/datasets", status_code=201)
def create_dataset(body: DatasetIn, user: User = CurrentUser, db: Session = DB) -> dict:
    if db.scalar(select(func.count()).select_from(RagDataset).where(RagDataset.owner_id == user.id)) >= 10:
        raise AppError("You can have up to 10 datasets. Delete one to create another.", code="limit")
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:60] + "-" + secrets.token_hex(3)
    ds = RagDataset(slug=slug, name=body.name.strip(), description=body.description, owner_id=user.id,
                    organization_id=user.organization_id, is_public=False)
    db.add(ds)
    db.flush()
    audit(db, user, "rag_dataset.create", "rag_dataset", ds.id)
    db.commit()
    return {"id": str(ds.id), "slug": ds.slug}


@router.get("/datasets/{key}")
def get_dataset(key: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    ds = _dataset(db, key, user)
    groups = set(groups_for(user))
    docs = db.scalars(select(RagDocument).where(RagDocument.dataset_id == ds.id).order_by(RagDocument.title)).all()
    qs = db.scalars(select(RagQuestion).where(RagQuestion.dataset_id == ds.id)).all()
    indexes = db.scalars(select(RagIndex).where(RagIndex.dataset_id == ds.id).order_by(RagIndex.created_at.desc()).limit(10)).all()

    def readable(d: RagDocument) -> bool:
        return "everyone" in (d.allowed_groups or []) or bool(groups & set(d.allowed_groups or []))

    return {"id": str(ds.id), "slug": ds.slug, "name": ds.name, "description": ds.description,
            "mine": user is not None and ds.owner_id == user.id,
            "documents": [{"id": str(d.id), "title": d.title, "source": d.source, "mime": d.mime, "allowed_groups": d.allowed_groups,
                           "words": len(d.text.split()), "readable": readable(d),
                           "preview": d.text[:600] if readable(d) else None} for d in docs],
            "questions": [{"question": q.question, "relevant_sources": q.relevant_sources, "user_groups": q.user_groups} for q in qs],
            "indexes": [{"config": i.config, "chunks": i.chunk_count, "backend": i.backend, "build_ms": i.build_ms} for i in indexes],
            "your_groups": sorted(groups)}


class DocumentIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    filename: str = Field("", max_length=300)
    text: str | None = Field(None, max_length=MAX_UPLOAD_BYTES)
    pdf_base64: str | None = Field(None, max_length=MAX_UPLOAD_BYTES * 2)
    allowed_groups: list[str] = Field(default_factory=lambda: ["everyone"], max_length=5)


def _pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise AppError("That file isn't a PDF.", code="bad_file", status_code=422)
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise AppError("PDF support isn't installed on this server.", code="pdf_unavailable", status_code=501) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 100:
            raise AppError("PDFs are limited to 100 pages.", code="too_large", status_code=413)
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed PDFs
        raise AppError("Couldn't read that PDF.", code="bad_file", status_code=422) from exc


@router.post("/datasets/{key}/documents", status_code=201)
def add_document(key: str, body: DocumentIn, user: User = CurrentUser, db: Session = DB) -> dict:
    ds = _owned(db, key, user)
    if db.scalar(select(func.count()).select_from(RagDocument).where(RagDocument.dataset_id == ds.id)) >= MAX_DOCS_PER_DATASET:
        raise AppError(f"A dataset can hold up to {MAX_DOCS_PER_DATASET} documents.", code="limit")
    ext = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if body.pdf_base64:
        try:
            raw = base64.b64decode(body.pdf_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AppError("The file data is not valid base64.", code="bad_file", status_code=422) from exc
        if len(raw) > MAX_UPLOAD_BYTES:
            raise AppError("Files are limited to 2 MB.", code="too_large", status_code=413)
        text, mime = _pdf_text(raw), "application/pdf"
    elif body.text is not None:
        if ext and ext not in ("md", "markdown", "txt", "text"):
            raise AppError("Upload .md, .txt or .pdf files.", code="bad_file", status_code=422)
        if len(body.text.encode()) > MAX_UPLOAD_BYTES:
            raise AppError("Files are limited to 2 MB.", code="too_large", status_code=413)
        text, mime = body.text, "text/markdown" if ext in ("md", "markdown") else "text/plain"
    else:
        raise AppError("Provide text or a PDF.", code="empty", status_code=422)
    text = clean_text(text)
    if len(text.split()) < 5:
        raise AppError("The document has no readable text.", code="empty", status_code=422)
    mine = set(groups_for(user))
    groups = [g.strip().lower() for g in body.allowed_groups if g.strip()] or ["everyone"]
    if not set(groups) <= mine:  # you can't grant access to groups you don't belong to
        raise AppError(f"You can only restrict documents to your own groups: {', '.join(sorted(mine))}.", code="bad_groups", status_code=422)
    h = hashlib.sha256(text.encode()).hexdigest()
    if db.scalar(select(RagDocument.id).where(RagDocument.dataset_id == ds.id, RagDocument.content_hash == h)):
        raise AppError("This document is already in the dataset.", code="duplicate", status_code=409)
    source = re.sub(r"[^a-z0-9]+", "-", (body.filename.rsplit(".", 1)[0] or body.title).lower()).strip("-")[:80]
    d = RagDocument(dataset_id=ds.id, title=body.title.strip(), source=source, mime=mime, text=text, content_hash=h,
                    allowed_groups=groups, created_by=user.id)
    db.add(d)
    db.flush()
    audit(db, user, "rag_document.create", "rag_document", d.id, after={"dataset": ds.slug, "groups": groups})
    track(db, user.id, "rag_upload", mode=mime)
    db.commit()
    return {"id": str(d.id), "words": len(text.split()), "mime": mime}


@router.delete("/datasets/{key}/documents/{doc_id}", status_code=204)
def delete_document(key: str, doc_id: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> None:
    ds = _owned(db, key, user)
    d = db.get(RagDocument, doc_id)
    if d is None or d.dataset_id != ds.id:
        raise NotFound("Document not found")
    db.delete(d)
    audit(db, user, "rag_document.delete", "rag_document", doc_id)
    db.commit()


class PreviewIn(BaseModel):
    document_id: uuid.UUID
    chunker: str = Field("markdown", pattern="^(" + "|".join(STRATEGIES) + ")$")
    size: int = Field(120, ge=20, le=1000)
    overlap: int = Field(20, ge=0, le=500)


@router.post("/datasets/{key}/chunk-preview")
def chunk_preview(key: str, body: PreviewIn, user: User | None = OptionalUser, db: Session = DB) -> dict:
    ds = _dataset(db, key, user)
    d = db.get(RagDocument, body.document_id)
    groups = set(groups_for(user))
    if d is None or d.dataset_id != ds.id or not ("everyone" in d.allowed_groups or groups & set(d.allowed_groups)):
        raise NotFound("Document not found")
    pieces = chunk(d.text, body.chunker, body.size, body.overlap)
    return {"document": d.title, "chunks": [{"n": i + 1, "text": p.text, "heading": p.heading, "words": p.words, "start": p.start,
                                             "end": p.end} for i, p in enumerate(pieces)],
            "stats": {"count": len(pieces), "avg_words": round(sum(p.words for p in pieces) / len(pieces)) if pieces else 0}}


class QueryIn(BaseModel):
    dataset: str
    question: str = Field(..., min_length=3, max_length=1000)
    chunker: str = Field("markdown", pattern="^(" + "|".join(STRATEGIES) + ")$")
    size: int = Field(120, ge=20, le=1000)
    overlap: int = Field(20, ge=0, le=500)
    embedder: str = Field("hashing-384", pattern="^(hashing-384|minilm-384|openai-small-384)$")
    strategy: str = Field("hybrid", pattern="^(vector|keyword|hybrid)$")
    top_k: int = Field(4, ge=1, le=12)
    rerank: bool = True
    generate: bool = True
    live: bool = True
    system_prompt: str | None = Field(None, max_length=4000)
    user_template: str | None = Field(None, max_length=4000)


def _cfg(body: Any) -> dict[str, Any]:
    return {"chunker": body.chunker, "size": body.size, "overlap": body.overlap, "embedder": body.embedder}


def _check_embedder(db: Session, user: User, embedder: str) -> None:
    opts = {e["key"]: e for e in embeddings.available(plan_for(db, user) != "free")}
    if not opts.get(embedder, {}).get("available"):
        raise AppError(f"The {embedder} embedder isn't available: {opts.get(embedder, {}).get('note', '')}", code="embedder_unavailable",
                       status_code=422)


@router.post("/query", dependencies=[Depends(rate_limit("rag", "rate_limit_agent_runs_per_minute"))])
def run_query(body: QueryIn, user: User = CurrentUser, db: Session = DB) -> dict:
    ds = _dataset(db, body.dataset, user)
    _check_embedder(db, user, body.embedder)
    enforce_quota(db, user, "rag_queries_per_day", "rag_query")
    choice = provider_for(db, user, body.live) if body.generate else None
    if body.user_template and ("{{passages}}" not in body.user_template or "{{question}}" not in body.user_template):
        raise AppError("The prompt template must include {{passages}} and {{question}}.", code="bad_template", status_code=422)
    r = query(db, ds, body.question, _cfg(body), groups_for(user), choice.provider if choice else None, body.strategy, body.top_k,
              body.rerank, body.system_prompt, body.user_template)
    r["mode"] = choice.mode if choice else None
    r["provider_label"] = choice.label if choice else None
    track(db, user.id, "rag_query", mode=body.strategy)
    db.commit()
    return r


class EvalIn(BaseModel):
    dataset: str
    chunker: str = Field("markdown", pattern="^(" + "|".join(STRATEGIES) + ")$")
    size: int = Field(120, ge=20, le=1000)
    overlap: int = Field(20, ge=0, le=500)
    embedder: str = Field("hashing-384", pattern="^(hashing-384|minilm-384|openai-small-384)$")
    strategy: str = Field("hybrid", pattern="^(vector|keyword|hybrid)$")
    top_k: int = Field(4, ge=1, le=12)
    rerank: bool = True
    generate: bool = False
    live: bool = True


@router.post("/evaluate", dependencies=[Depends(rate_limit("rag", "rate_limit_agent_runs_per_minute"))])
def run_eval(body: EvalIn, user: User = CurrentUser, db: Session = DB) -> dict:
    ds = _dataset(db, body.dataset, user)
    _check_embedder(db, user, body.embedder)
    n = db.scalar(select(func.count()).select_from(RagQuestion).where(RagQuestion.dataset_id == ds.id)) or 0
    enforce_quota(db, user, "rag_queries_per_day", "rag_query", cost=max(1, n))
    choice = provider_for(db, user, body.live) if body.generate else None
    r = evaluate(db, ds, _cfg(body), choice.provider if choice else None, body.strategy, body.top_k, body.rerank)
    label = f"{ds.name}: {body.strategy}, {body.chunker} {body.size}/{body.overlap}, top-{body.top_k}{', rerank' if body.rerank else ''}"
    ev = Evaluation(name=label[:200], target_type="rag", target_id=ds.id, created_by=user.id,
                    summary={"kind": "rag_eval", "metrics": r.get("metrics", {}), "config": r.get("config"), "strategy": body.strategy,
                             "top_k": body.top_k, "rerank": body.rerank, "generate": body.generate, "dataset": ds.slug,
                             "passed": r.get("passed"), "total": r.get("total"), "mode": choice.mode if choice else None})
    db.add(ev)
    db.flush()
    for c in r.get("cases", []):
        db.add(EvaluationCase(evaluation_id=ev.id, case_key=c["question"][:100], input={"question": c["question"], "groups": c["groups"]},
                              expected={"relevant": c["relevant"]}, result=c, passed=c["passed"]))
    track(db, user.id, "rag_eval", mode=body.strategy)
    db.commit()
    return {"evaluation_id": str(ev.id), **r}
