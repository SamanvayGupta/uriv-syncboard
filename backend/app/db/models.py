"""
uriv-syncboard / backend / app / db / models.py
─────────────────────────────────────────────────
SQLAlchemy 2.x declarative models.

Schema
──────
boards
  └── sessions  (many per board)
        └── notes  (one per captured page)

A *board* is a physical whiteboard.
A *session* is one recording sitting.
A *note*    is one captured state of the board (= one page export).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, Float, ForeignKey,
    Integer, LargeBinary, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── boards ────────────────────────────────────────────────────────────────────

class Board(Base):
    __tablename__ = "boards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name:       Mapped[str]      = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="board", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Board id={self.id} name={self.name!r}>"


# ── sessions ──────────────────────────────────────────────────────────────────

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boards.id", ondelete="CASCADE")
    )
    name:       Mapped[str]      = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at:   Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    board: Mapped["Board"]       = relationship("Board", back_populates="sessions")
    notes: Mapped[list["Note"]]  = relationship(
        "Note", back_populates="session",
        order_by="Note.sequence_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} name={self.name!r}>"


# ── notes ─────────────────────────────────────────────────────────────────────

class Note(Base):
    """
    One captured whiteboard state (= one 'page').

    sequence_order  — monotonically increasing within a session;
                      allows timeline reconstruction.
    image_data      — raw PNG/JPEG bytes (stored in DB for portability).
                      Large deployments should swap to object-storage
                      and store only a URL here.
    ocr_text        — full plain-text OCR result.
    confidence      — average word-level confidence 0-100.
    """

    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    sequence_order: Mapped[int]   = mapped_column(Integer, nullable=False)
    created_at:     Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ocr_text:   Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float]      = mapped_column(Float, default=0.0)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    session: Mapped["Session"] = relationship("Session", back_populates="notes")

    def __repr__(self) -> str:
        return (
            f"<Note id={self.id} seq={self.sequence_order} "
            f"conf={self.confidence:.1f}>"
        )
