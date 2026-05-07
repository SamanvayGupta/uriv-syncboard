"""
uriv-syncboard / backend / app / core / camera.py
──────────────────────────────────────────────────
Stream ingestion layer.

Supports three source types:
  • WEBCAM  — live camera device (V4L2 on Linux, DSHOW on Windows, AVFoundation on macOS)
  • VIDEO   — pre-recorded file (.mp4 / .avi / .mov / .mkv)
  • IMAGES  — ordered list of still images (batch processing)

Windows note:
  cv2.VideoCapture on Windows often needs the DirectShow (DSHOW) backend flag.
  We try the default backend first, then fall back to CAP_DSHOW automatically.
"""

from __future__ import annotations

import logging
import platform
import time
from enum import Enum
from pathlib import Path
from threading import Event, Lock
from typing import Iterator, List, Optional, Union

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"


class SourceType(str, Enum):
    WEBCAM = "webcam"
    VIDEO  = "video"
    IMAGES = "images"


class CameraStream:
    """
    Unified frame iterator over webcam / video / image sources.

    Parameters
    ----------
    source_type : SourceType
    source      : int (webcam index) | str/Path (file) | list[str] (images)
    fps_cap     : max frames per second to emit
    """

    def __init__(
        self,
        source_type: SourceType,
        source: Union[int, str, Path, List[str]],
        fps_cap: int = 30,
    ):
        self.source_type = source_type
        self.source      = source
        self.fps_cap     = fps_cap

        self._cap        = None
        self._img_list:  List = []
        self._img_cursor = 0

        self._running = Event()
        self._lock    = Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> "CameraStream":
        self._running.set()

        if self.source_type == SourceType.WEBCAM:
            self._cap = self._open_webcam(int(self.source))

        elif self.source_type == SourceType.VIDEO:
            try:
                import cv2
            except ImportError:
                raise RuntimeError("opencv-python-headless not installed")
            self._cap = cv2.VideoCapture(str(self.source))
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open video: {self.source}")
            log.info("Video opened: %s", self.source)

        elif self.source_type == SourceType.IMAGES:
            try:
                import cv2
            except ImportError:
                raise RuntimeError("opencv-python-headless not installed")
            paths = self.source if isinstance(self.source, list) else [self.source]
            loaded = []
            for p in paths:
                img = cv2.imread(str(p))
                if img is not None:
                    loaded.append(img)
                    log.debug("Loaded image: %s", p)
                else:
                    log.warning("Could not load image: %s", p)
            if not loaded:
                raise RuntimeError("No images could be loaded from the provided paths")
            self._img_list   = loaded
            self._img_cursor = 0
            log.info("Image batch loaded: %d frames", len(loaded))

        return self

    def _open_webcam(self, index: int):
        """
        Open webcam with platform-appropriate backend.

        Windows:  try default first, then CAP_DSHOW (DirectShow).
        Linux:    default (V4L2).
        macOS:    default (AVFoundation) — Docker can't reach this.
        """
        try:
            import cv2
        except ImportError:
            raise RuntimeError("opencv-python-headless not installed")

        # Try default backend first
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            log.info("Webcam %d opened (default backend)", index)
            return cap
        cap.release()

        # FIX: Windows fallback — DirectShow backend
        if IS_WINDOWS:
            log.info("Default backend failed — trying CAP_DSHOW for webcam %d", index)
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap.isOpened():
                log.info("Webcam %d opened with CAP_DSHOW", index)
                return cap
            cap.release()

        raise RuntimeError(
            f"Cannot open webcam index {index}. "
            f"Check that the camera is connected and not used by another app "
            f"(Zoom, Teams, Camera app, etc.)."
        )

    def stop(self):
        self._running.clear()
        with self._lock:
            if self._cap:
                self._cap.release()
                self._cap = None
        log.info("CameraStream stopped.")

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    # ── Iterator ──────────────────────────────────────────────────────────────

    def __iter__(self) -> Iterator:
        interval = 1.0 / max(self.fps_cap, 1)

        while self._running.is_set():
            t_start = time.monotonic()
            frame   = self._next_frame()
            if frame is None:
                break
            yield frame
            elapsed = time.monotonic() - t_start
            sleep   = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def _next_frame(self):
        if self.source_type in (SourceType.WEBCAM, SourceType.VIDEO):
            with self._lock:
                if self._cap is None:
                    return None
                ret, frame = self._cap.read()
            if not ret:
                log.info("Stream ended (read returned False).")
                return None
            return frame

        elif self.source_type == SourceType.IMAGES:
            if self._img_cursor >= len(self._img_list):
                log.info("All images processed.")
                self._running.clear()
                return None
            frame = self._img_list[self._img_cursor]
            self._img_cursor += 1
            time.sleep(1.5)   # hold each image so OCR has time to run
            return frame

        return None

    # ── Metadata ──────────────────────────────────────────────────────────────

    @property
    def frame_dimensions(self):
        try:
            import cv2
            if self._cap and self._cap.isOpened():
                w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                return w, h
        except Exception:
            pass
        if self._img_list:
            h, w = self._img_list[0].shape[:2]
            return w, h
        return None

    @property
    def total_frames(self):
        try:
            import cv2
            if self.source_type == SourceType.VIDEO and self._cap:
                n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
                return n if n > 0 else None
        except Exception:
            pass
        if self.source_type == SourceType.IMAGES:
            return len(self._img_list)
        return None
