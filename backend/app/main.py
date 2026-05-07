"""
uriv-syncboard / backend / app / main.py
────────────────────────────────────────
FastAPI application factory.

DB connection is optional — the app starts even without PostgreSQL.
Webcam, OCR, and export all work in no-DB mode.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ws import router as ws_router
from app.api.routes import router as rest_router
from app.core.config import settings
from app.db.session import engine
from app.db.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger("syncboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Try to connect to PostgreSQL and create tables.
    If the DB is unavailable, log a warning and continue —
    webcam, OCR, capture and export all still work.
    Only session persistence to the DB will be skipped.
    """
    log.info("Starting SyncBoard backend …")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Database tables ready.")
    except Exception as exc:
        log.warning(
            "PostgreSQL not reachable (%s: %s). "
            "Running in NO-DB mode — webcam/OCR/export work fine. "
            "To enable persistence: docker compose up postgres -d",
            type(exc).__name__, exc,
        )
    yield
    log.info("Shutting down SyncBoard backend …")
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="SyncBoard API",
    description="Smart Whiteboard OCR — WebSocket + REST",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(rest_router, prefix="/api")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
