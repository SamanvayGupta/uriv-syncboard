"""
uriv-syncboard / backend / app / core / config.py
──────────────────────────────────────────────────
Central settings — all values overridable via env vars or .env file.
"""

from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard"
    )

    # ── CORS ────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    # ── OCR ─────────────────────────────────────────────────────
    # FIX: default is now "tesseract" — paddle requires 2 GB download on first run.
    # Set OCR_ENGINE=paddle in .env if you want the heavier but more accurate model.
    ocr_engine: str     = "tesseract"
    min_confidence: int = 30            # lowered: 40 was too strict for whiteboards

    # ── Vision ──────────────────────────────────────────────────
    ocr_width: int          = 1280
    clear_threshold: float  = 0.05
    block_size: int         = 21
    block_c: int            = 10
    debounce_frames: int    = 3

    # ── Capture ─────────────────────────────────────────────────
    fps_cap: int        = 30
    ocr_interval: float = 0.8          # slightly longer — reduces CPU spike

    # ── Export ──────────────────────────────────────────────────
    export_dir: str = "/tmp/syncboard_exports"


settings = Settings()
