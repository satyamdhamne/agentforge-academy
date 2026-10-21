"""Phase 4: prompt lab test cases and the RAG lab (datasets, documents, indexes, chunks, labelled questions)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDPk

# ---------------------------------------------------------------------------- prompt lab


class PromptTestCase(UUIDPk, Base):
    """A labelled input for a prompt template plus the assertions its output must satisfy."""

    __tablename__ = "prompt_test_cases"
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    variables: Mapped[dict[str, Any]] = mapped_column(default=dict)
    assertions: Mapped[list[Any]] = mapped_column(default=list)
    order_index: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------- RAG lab


class RagDataset(UUIDPk, Timestamps, Base):
    """A document collection. owner_id NULL = shared demo corpus (read-only for learners)."""

    __tablename__ = "rag_datasets"
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)


class RagDocument(UUIDPk, Base):
    __tablename__ = "rag_documents"
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_datasets.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(300), default="")
    mime: Mapped[str] = mapped_column(String(100), default="text/markdown")
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    # Document-level permissions: a user sees a document only if they share one of these groups.
    allowed_groups: Mapped[list[Any]] = mapped_column(default=lambda: ["everyone"])
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("dataset_id", "content_hash", name="uq_rag_documents_dataset_hash"),)


class RagIndex(UUIDPk, Base):
    """One index per (dataset, chunking + embedding configuration). Rebuilt when documents change."""

    __tablename__ = "rag_indexes"
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_datasets.id", ondelete="CASCADE"), index=True)
    config: Mapped[dict[str, Any]] = mapped_column()
    config_hash: Mapped[str] = mapped_column(String(64))
    corpus_hash: Mapped[str] = mapped_column(String(64))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    build_ms: Mapped[int] = mapped_column(Integer, default=0)
    backend: Mapped[str] = mapped_column(String(20), default="python")  # pgvector | python
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("dataset_id", "config_hash", name="uq_rag_indexes_dataset_config"),)


class RagChunk(UUIDPk, Base):
    """Chunk text and its embedding. When pgvector is installed, migration 0002 also adds an
    `embedding_vec vector(384)` column with an HNSW index (managed outside the ORM)."""

    __tablename__ = "rag_chunks"
    index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_indexes.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    start_char: Mapped[int] = mapped_column(Integer, default=0)
    end_char: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(String(300), default="")
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float))

    __table_args__ = (Index("ix_rag_chunks_index_ordinal", "index_id", "ordinal"),)


class RagQuestion(UUIDPk, Base):
    """Labelled evaluation question: which documents are relevant and what the answer must contain."""

    __tablename__ = "rag_questions"
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_datasets.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    relevant_sources: Mapped[list[Any]] = mapped_column(default=list)  # document `source` keys
    answer_contains: Mapped[list[Any]] = mapped_column(default=list)
    user_groups: Mapped[list[Any]] = mapped_column(default=lambda: ["everyone"])
