"""
uriv-syncboard / backend / app / api / ws.py
─────────────────────────────────────────────
WebSocket endpoint.

FIXES in this version
──────────────────────
1. db_session_id is now sent to the frontend in every session_update message
   so the export REST calls can use it.
2. Camera failure is caught and reported as a status message (not a silent crash).
3. Thread event loop is properly closed on exit.
4. DB session is reused across all pages in a session (not recreated per page).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.camera import CameraStream, SourceType
from app.core.config import settings
from app.core.processor import FrameProcessor
from app.core.tracker import BoardTracker
from app.db.session import AsyncSessionLocal
from app.db.models import Board, Session as DBSession, Note

log    = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# Lazy cv2 import helper
# ══════════════════════════════════════════════════════════════════════════════

def _cv2():
    import cv2
    return cv2


# ══════════════════════════════════════════════════════════════════════════════
# In-memory page model
# ══════════════════════════════════════════════════════════════════════════════

class PageSnapshot:
    def __init__(self, seq: int, frame, text: str, confidence: float):
        self.seq        = seq
        self.frame      = frame
        self.text       = text
        self.confidence = confidence
        self.ts         = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "seq":        self.seq,
            "text":       self.text,
            "confidence": round(self.confidence, 1),
            "timestamp":  self.ts.isoformat(),
        }

    def png_bytes(self) -> bytes:
        cv2 = _cv2()
        _, buf = cv2.imencode(".png", self.frame)
        return buf.tobytes()


# ══════════════════════════════════════════════════════════════════════════════
# Per-connection orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class CaptureOrchestrator:

    def __init__(self, ws: WebSocket):
        self.ws        = ws
        self.processor = FrameProcessor()
        self.tracker   = BoardTracker()

        self._camera:  Optional[CameraStream]     = None
        self._thread:  Optional[threading.Thread] = None
        self._running  = threading.Event()

        self.auto_detect = False
        self.pages:   List[PageSnapshot] = []
        self._seq     = 0
        self._session_name = f"Session {datetime.now(timezone.utc).strftime('%b %d %H:%M')}"

        # FIX: DB references cached and sent to frontend
        self._db_board_id:   Optional[uuid.UUID] = None
        self._db_session_id: Optional[uuid.UUID] = None

        self._last_ocr_time  = 0.0
        self._current_frame  = None

    # ── Messaging ─────────────────────────────────────────────────────────────

    async def _send(self, msg: Dict[str, Any]):
        try:
            await self.ws.send_text(json.dumps(msg, default=str))
        except Exception:
            pass

    async def _status(self, message: str, level: str = "info"):
        await self._send({"type": "status", "message": message, "level": level})

    # ── Stream control ────────────────────────────────────────────────────────

    def start_stream(self, source_type: SourceType, source):
        self._stop_stream()
        self._running.set()
        try:
            self._camera = CameraStream(source_type, source, fps_cap=settings.fps_cap)
            self._camera.start()
        except Exception as exc:
            self._running.clear()
            # Schedule status message in calling async context
            log.error("Camera failed to open: %s", exc)
            raise

        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True,
            name=f"capture_{id(self)}",
        )
        self._thread.start()

    def _stop_stream(self):
        self._running.clear()
        if self._camera:
            self._camera.stop()
            self._camera = None

    def stop(self):
        self._stop_stream()

    # ── Capture loop (daemon thread) ──────────────────────────────────────────

    def _capture_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            for frame in self._camera:
                if not self._running.is_set():
                    break

                self._current_frame = frame.copy()

                # Send display thumbnail
                b64 = self._encode_jpeg(self._thumbnail(frame))
                loop.run_until_complete(
                    self._send({"type": "frame", "data": b64})
                )

                # Throttled OCR
                now = time.monotonic()
                if now - self._last_ocr_time < settings.ocr_interval:
                    continue
                self._last_ocr_time = now

                result = self.processor.run(frame)
                loop.run_until_complete(self._send({
                    "type":       "ocr_update",
                    "text":       result.text,
                    "confidence": round(result.confidence, 1),
                    "lines": [
                        {"text": l.text, "confidence": round(l.confidence, 1)}
                        for l in result.lines
                    ],
                }))

                event = self.tracker.update(frame, result.text)
                if event == "BOARD_CLEARED":
                    loop.run_until_complete(self._handle_board_cleared(frame))
                elif event == "TEXT_STABLE":
                    loop.run_until_complete(
                        self._send({"type": "text_stable", "text": result.text})
                    )

        except Exception as exc:
            log.error("Capture loop error: %s", exc, exc_info=True)
            loop.run_until_complete(
                self._status(f"Stream error: {exc}", "error")
            )
        finally:
            loop.close()

    async def _handle_board_cleared(self, frame):
        await self._send({"type": "board_cleared"})
        if self.auto_detect and self.pages:
            last = self.pages[-1]
            if last.text.strip():
                await self._flush_page_to_db(last)
        self.tracker.reset_text_buffer()
        self.tracker.set_reference(frame)

    # ── Page management ───────────────────────────────────────────────────────

    async def capture_page(self) -> Optional[PageSnapshot]:
        if self._current_frame is None:
            await self._status("No frame yet — start a source first.", "error")
            return None

        result    = self.processor.run(self._current_frame)
        self._seq += 1
        snap      = PageSnapshot(
            self._seq, self._current_frame.copy(),
            result.text, result.confidence,
        )
        self.pages.append(snap)

        await self._send({"type": "page_captured", "page": snap.to_dict()})
        await self._send_session_update()     # includes db_session_id
        await self._flush_page_to_db(snap)
        await self._status(f"Page {self._seq} captured.", "success")
        return snap

    async def delete_page(self, seq: int):
        self.pages = [p for p in self.pages if p.seq != seq]
        await self._send_session_update()
        await self._status(f"Page {seq} deleted.", "info")

    def new_session(self):
        self.pages          = []
        self._seq           = 0
        self._db_board_id   = None
        self._db_session_id = None
        self._session_name  = f"Session {datetime.now(timezone.utc).strftime('%b %d %H:%M')}"
        self.tracker.reset_text_buffer()

    async def _send_session_update(self):
        """
        FIX: db_session_id is now included so the frontend can call export endpoints.
        """
        await self._send({
            "type": "session_update",
            "session": {
                "name":          self._session_name,
                "page_count":    len(self.pages),
                "pages":         [p.to_dict() for p in self.pages],
                "db_session_id": str(self._db_session_id) if self._db_session_id else None,
            },
        })

    # ── DB persistence ────────────────────────────────────────────────────────

    async def _ensure_db_session(self, db) -> uuid.UUID:
        """Create Board+Session once; reuse UUID for all subsequent pages."""
        if self._db_session_id is not None:
            return self._db_session_id

        board = Board(name="Default Board")
        db.add(board)
        await db.flush()
        self._db_board_id = board.id

        sess = DBSession(board_id=board.id, name=self._session_name)
        db.add(sess)
        await db.flush()
        self._db_session_id = sess.id
        log.info("Created DB session %s", self._db_session_id)
        return self._db_session_id

    async def _flush_page_to_db(self, snap: PageSnapshot):
        try:
            async with AsyncSessionLocal() as db:
                session_id = await self._ensure_db_session(db)
                note = Note(
                    session_id     = session_id,
                    sequence_order = snap.seq,
                    ocr_text       = snap.text,
                    confidence     = snap.confidence,
                    image_data     = snap.png_bytes(),
                )
                db.add(note)
                await db.commit()
                log.info("Saved note seq=%d", snap.seq)
                # Re-send session update now that db_session_id is definitely set
                await self._send_session_update()
        except Exception as exc:
            log.error("DB flush failed: %s", exc, exc_info=True)

    # ── Frame utilities ───────────────────────────────────────────────────────

    @staticmethod
    def _thumbnail(frame, max_w: int = 960):
        cv2 = _cv2()
        h, w = frame.shape[:2]
        if w <= max_w:
            return frame
        return cv2.resize(frame, (max_w, int(h * max_w / w)),
                          interpolation=cv2.INTER_AREA)

    @staticmethod
    def _encode_jpeg(frame, quality: int = 70) -> str:
        cv2 = _cv2()
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf.tobytes()).decode()


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket route
# ══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    orch = CaptureOrchestrator(ws)
    log.info("WebSocket connected: %s", ws.client)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t   = msg.get("type", "")

            if t == "start_webcam":
                idx = int(msg.get("device_index", 0))
                try:
                    orch.start_stream(SourceType.WEBCAM, idx)
                    await orch._status(f"Webcam {idx} started.", "success")
                except Exception as exc:
                    await orch._status(
                        f"Cannot open webcam {idx}. "
                        f"Check it's connected and not used by another app. ({exc})",
                        "error"
                    )

            elif t == "start_video":
                try:
                    orch.start_stream(SourceType.VIDEO, msg["path"])
                    await orch._status("Video started.", "success")
                except Exception as exc:
                    await orch._status(f"Cannot open video: {exc}", "error")

            elif t == "start_images":
                paths = msg["paths"]
                try:
                    orch.start_stream(SourceType.IMAGES, paths)
                    await orch._status(f"Processing {len(paths)} image(s)…", "info")
                except Exception as exc:
                    await orch._status(f"Cannot load images: {exc}", "error")

            elif t == "stop":
                orch.stop()
                await orch._status("Capture stopped.", "info")

            elif t == "set_roi":
                orch.processor.set_roi(msg["x"], msg["y"], msg["w"], msg["h"])
                await orch._status("ROI applied.", "success")

            elif t == "clear_roi":
                orch.processor.clear_roi()
                await orch._status("ROI cleared.", "info")

            elif t == "capture_page":
                await orch.capture_page()

            elif t == "set_reference":
                if orch._current_frame is not None:
                    orch.tracker.set_reference(orch._current_frame)
                    await orch._status("Reference frame set.", "success")
                else:
                    await orch._status("No frame yet — start a source first.", "error")

            elif t == "toggle_auto":
                orch.auto_detect = bool(msg.get("enabled", False))
                await orch._status(
                    f"Auto-detect {'enabled' if orch.auto_detect else 'disabled'}.", "info"
                )

            elif t == "delete_page":
                await orch.delete_page(int(msg["page_id"]))

            elif t == "new_session":
                orch.new_session()
                await orch._send_session_update()
                await orch._status("New session started.", "info")

            elif t == "ping":
                await orch._send({"type": "pong"})

    except WebSocketDisconnect:
        log.info("WebSocket disconnected.")
    except Exception as exc:
        log.exception("WebSocket error: %s", exc)
    finally:
        orch.stop()
