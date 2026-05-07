"""
uriv-syncboard / backend / app / api / routes.py
──────────────────────────────────────────────────
REST API — sessions management + multi-format export + file upload.

Endpoints
─────────
GET  /api/sessions                   — list all sessions
GET  /api/sessions/{sid}             — single session + pages
DELETE /api/sessions/{sid}           — delete a session

GET  /api/sessions/{sid}/export/{fmt}
        fmt = pdf | docx | pptx | markdown | txt | json

POST /api/upload                     — upload video or images for processing
     Returns: { "paths": ["/tmp/..."] }
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import Session as DBSession, Note
from app.services.exporter import ExportService

log    = logging.getLogger(__name__)
router = APIRouter()

ExportFmt = Literal["pdf", "docx", "pptx", "markdown", "txt", "json"]

MEDIA_TYPES = {
    "pdf":      "application/pdf",
    "docx":     "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx":     "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "markdown": "text/markdown",
    "txt":      "text/plain",
    "json":     "application/json",
}

UPLOAD_DIR = Path("/tmp/syncboard_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions", tags=["sessions"])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBSession).order_by(DBSession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id":         str(s.id),
            "name":       s.name,
            "started_at": s.started_at.isoformat(),
            "page_count": len(s.notes),
        }
        for s in sessions
    ]


@router.get("/sessions/{sid}", tags=["sessions"])
async def get_session(sid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result  = await db.execute(
        select(DBSession)
        .options(selectinload(DBSession.notes))
        .where(DBSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "id":         str(session.id),
        "name":       session.name,
        "started_at": session.started_at.isoformat(),
        "pages": [
            {
                "id":             str(n.id),
                "sequence_order": n.sequence_order,
                "ocr_text":       n.ocr_text,
                "confidence":     n.confidence,
                "created_at":     n.created_at.isoformat(),
            }
            for n in session.notes
        ],
    }


@router.delete("/sessions/{sid}", tags=["sessions"])
async def delete_session(sid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result  = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    await db.delete(session)
    return {"deleted": str(sid)}


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/sessions/{sid}/export/{fmt}", tags=["export"])
async def export_session(
    sid: uuid.UUID,
    fmt: ExportFmt,
    db:  AsyncSession = Depends(get_db),
):
    result  = await db.execute(
        select(DBSession)
        .options(selectinload(DBSession.notes))
        .where(DBSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    if not session.notes:
        raise HTTPException(400, "Session has no pages to export.")

    exporter = ExportService(session)
    buf      = exporter.build(fmt)
    ext      = "md" if fmt == "markdown" else fmt
    filename = f"{_safe_name(session.name)}.{ext}"

    return StreamingResponse(
        io.BytesIO(buf),
        media_type = MEDIA_TYPES[fmt],
        headers    = {"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── File upload ───────────────────────────────────────────────────────────────

@router.post("/upload", tags=["upload"])
async def upload_files(files: list[UploadFile] = File(...)):
    saved_paths = []
    for f in files:
        dest = UPLOAD_DIR / f.filename
        content = await f.read()
        dest.write_bytes(content)
        saved_paths.append(str(dest))
        log.info("Uploaded: %s (%d bytes)", dest.name, len(content))

    return {"paths": saved_paths, "count": len(saved_paths)}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
