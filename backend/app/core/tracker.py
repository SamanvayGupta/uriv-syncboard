"""
uriv-syncboard / backend / app / core / tracker.py
────────────────────────────────────────────────────
Frame-differencing engine that detects "board wipe" events.

Algorithm
─────────
1. A *reference frame* is stored when the user declares "this is the clean board."
2. On every incoming frame, the absolute per-pixel difference vs the reference
   is computed and thresholded (30 greyscale units).
3. If the fraction of non-zero (changed) pixels drops below `clear_threshold`
   (default 5%), the board is considered "back to clean" → BOARD_CLEARED fires.
4. A *debounce* counter prevents spurious repeated events:
   the event fires only once per continuous "clean" region.

Text debounce
─────────────
A secondary responsibility is debouncing OCR output so the frontend only
receives a new text update when the board content has stabilised.

Public API
──────────
tracker = BoardTracker()
tracker.set_reference(frame)

event = tracker.update(frame, ocr_text)
# event is None | "BOARD_CLEARED" | "TEXT_STABLE"
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Literal, Optional

import cv2
import numpy as np

from app.core.config import settings

log = logging.getLogger(__name__)

Event = Literal["BOARD_CLEARED", "TEXT_STABLE"]

_PROCESS_SIZE = (640, 480)  # resize before diff to reduce compute


class BoardTracker:
    """Stateful frame-diff tracker."""

    def __init__(self):
        self._reference:    Optional[np.ndarray] = None
        self._was_cleared:  bool                 = False

        # Text debounce — keep last N OCR outputs
        self._text_buffer:  Deque[str] = deque(maxlen=settings.debounce_frames)
        self._last_stable:  str        = ""

    # ── Reference management ──────────────────────────────────────────────────

    def set_reference(self, frame: np.ndarray):
        """Store a 'clean board' reference frame."""
        grey = self._to_grey(frame)
        self._reference   = grey
        self._was_cleared = False
        log.info("Reference frame updated.")

    def has_reference(self) -> bool:
        return self._reference is not None

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, ocr_text: str) -> Optional[Event]:
        """
        Call once per processed frame.

        Returns
        -------
        "BOARD_CLEARED"  — board just returned to reference state
        "TEXT_STABLE"    — OCR text has been identical for N consecutive frames
        None             — no notable event
        """
        event = self._check_clear(frame)
        if event:
            return event

        return self._check_text_stable(ocr_text)

    # ── Board-clear detection ─────────────────────────────────────────────────

    def _check_clear(self, frame: np.ndarray) -> Optional[Event]:
        if self._reference is None:
            return None

        grey  = self._to_grey(frame)
        diff  = cv2.absdiff(grey, self._reference)
        _, th = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        ratio = float(np.count_nonzero(th)) / th.size

        log.debug("Frame diff ratio: %.4f  (threshold %.4f)", ratio, settings.clear_threshold)

        if ratio < settings.clear_threshold:
            if not self._was_cleared:
                self._was_cleared = True
                log.info("BOARD_CLEARED detected (diff ratio %.4f)", ratio)
                return "BOARD_CLEARED"
        else:
            self._was_cleared = False

        return None

    # ── Text stabilisation ────────────────────────────────────────────────────

    def _check_text_stable(self, text: str) -> Optional[Event]:
        """Emit TEXT_STABLE when the same non-empty text appears N times."""
        self._text_buffer.append(text.strip())

        if len(self._text_buffer) < self._text_buffer.maxlen:
            return None

        # All N frames identical AND non-empty?
        if (
            len(set(self._text_buffer)) == 1
            and self._text_buffer[-1]
            and self._text_buffer[-1] != self._last_stable
        ):
            self._last_stable = self._text_buffer[-1]
            return "TEXT_STABLE"

        return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_grey(frame: np.ndarray) -> np.ndarray:
        small = cv2.resize(frame, _PROCESS_SIZE, interpolation=cv2.INTER_AREA)
        if small.ndim == 3:
            return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return small

    def reset_text_buffer(self):
        """Clear text debounce (call after BOARD_CLEARED)."""
        self._text_buffer.clear()
        self._last_stable = ""
