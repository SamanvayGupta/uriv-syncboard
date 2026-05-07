# 🖊 uriv-syncboard

**Smart Whiteboard Assistant** — Computer Vision · Real-time OCR · Multi-format Export

Watches a whiteboard through a camera, reads everything on it with OCR, detects when the board gets wiped, auto-saves each "page", and exports the session as PDF, Word, PowerPoint, Markdown, plain text, or JSON.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI + Python 3.11 + WebSockets + asyncio |
| OCR | Tesseract (default) · PaddleOCR (optional) |
| Database | PostgreSQL 16 via SQLAlchemy 2 (async) + asyncpg |
| Infrastructure | Docker Compose (DB only on macOS) |

---

## Quick Start — macOS (Recommended)

> **Why not full Docker on macOS?**
> Docker Desktop on macOS runs inside a Linux VM with no USB passthrough.
> The backend must run locally so it can access your Mac's webcam.

### Step 1 — Install prerequisites (once)

```bash
brew install tesseract       # OCR engine
brew install node            # Node.js + npm
brew install python          # Python 3.11+
# Docker Desktop from https://docker.com/products/docker-desktop (for PostgreSQL)
```

### Step 2 — Run

```bash
unzip uriv-syncboard.zip && cd uriv-syncboard
chmod +x start_macos.sh
./start_macos.sh
```

The script:
1. Starts PostgreSQL in Docker (just the DB)
2. Creates a Python venv and installs backend deps
3. Starts the FastAPI backend locally (port 8000)
4. Installs npm packages and starts Vite (port 5173)
5. Opens **http://localhost:5173** in your browser automatically

---

## Quick Start — Linux (full Docker)

```bash
unzip uriv-syncboard.zip && cd uriv-syncboard
cp .env.example .env
docker compose up --build
# → http://localhost:5173
```

For webcam support on Linux, uncomment in `docker-compose.yml`:
```yaml
devices:
  - /dev/video0:/dev/video0
```

---

## Quick Start — Windows

```bat
unzip uriv-syncboard.zip
cd uriv-syncboard
start_local.bat
```

Prerequisites: Python 3.11+, Node 20+, Tesseract ([installer](https://github.com/UB-Mannheim/tesseract/wiki)), Docker Desktop (optional).

---

## How to Use the App

### 1. Choose a source

| Button | What it does |
|---|---|
| 📷 Webcam | Opens your default camera (index 0) |
| 🎬 Video | Upload a `.mp4 / .avi / .mov` file |
| 🖼 Images | Upload one or more `.png / .jpg` images |
| ⏹ Stop | Stops the active stream |

### 2. Set a Region of Interest (optional but recommended)

Click and drag on the live feed canvas to draw a rectangle around just the whiteboard. This:
- Improves OCR accuracy (ignores background)
- Reduces processing time significantly

Click **✂ Clear ROI** to remove it.

### 3. Set a reference frame

Show the camera an **empty, clean board**, then click **🔄 Set Reference**.

Once a reference is set, turn on **Auto-detect clears**. Every time the board is wiped back close to that reference state, the app automatically saves the current page.

### 4. Capture pages

- **Manual** — click **📸 Capture Page** at any time
- **Automatic** — enable Auto-detect and wipe the board

Each captured page appears in the **Session Pages** list. Click a page to preview it.

### 5. Export

Click any button in the **Export** section after capturing at least one page:

| Format | What you get |
|---|---|
| PDF | A4 report: cover page + per-page image + OCR text |
| Word (.docx) | Document with headings, embedded images, body text |
| PowerPoint | 16:9 slides — board image left, OCR text right |
| Markdown | GitHub-compatible `.md` with image links |
| Plain Text | Simple separator-delimited text dump |
| JSON | Structured data — pipe into databases or LLMs |

---

## Architecture

```
Browser (React + Vite)
    │
    │  WebSocket /ws  (frames + OCR + events)
    │  HTTP /api      (sessions + export + upload)
    ▼
FastAPI (Python)
    │
    ├── CameraStream     ← webcam / video / images iterator
    ├── FrameProcessor   ← resize → deskew → binarize → Tesseract OCR
    ├── BoardTracker     ← frame-diff board-clear + text debounce
    │
    └── PostgreSQL       ← boards → sessions → notes (images + OCR text)
```

### WebSocket message flow

**Client → Server**

| Message | Effect |
|---|---|
| `start_webcam` | Opens camera index 0 |
| `start_video` | Opens uploaded video file |
| `start_images` | Processes uploaded images one by one |
| `stop` | Stops the stream |
| `set_roi` | Crops frame before OCR |
| `clear_roi` | Removes crop |
| `capture_page` | Saves current frame as a page |
| `set_reference` | Stores current frame as "clean board" |
| `toggle_auto` | Enables/disables auto-capture on board wipe |
| `delete_page` | Removes a page from the session |
| `new_session` | Starts a fresh session |
| `ping` | Keepalive (every 25 s) |

**Server → Client**

| Message | Payload |
|---|---|
| `frame` | Base64 JPEG thumbnail (30 FPS) |
| `ocr_update` | `text`, `confidence`, `lines[]` |
| `page_captured` | `{seq, text, confidence, timestamp}` |
| `board_cleared` | (fires BOARD_CLEARED event) |
| `text_stable` | Debounced stable text |
| `session_update` | `{name, page_count, pages[], db_session_id}` |
| `status` | `{message, level: info/success/error}` |

---

## Project Structure

```
uriv-syncboard/
├── start_macos.sh              ← macOS one-command startup
├── start_local.sh              ← Linux/macOS manual startup
├── start_local.bat             ← Windows startup
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── .env                    ← local dev config (created by start script)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── app/
│       ├── main.py             ← FastAPI app + lifespan
│       ├── core/
│       │   ├── config.py       ← Pydantic settings from .env
│       │   ├── camera.py       ← CameraStream (webcam/video/images)
│       │   ├── processor.py    ← FrameProcessor (binarize + OCR)
│       │   └── tracker.py      ← BoardTracker (frame-diff + debounce)
│       ├── api/
│       │   ├── ws.py           ← WebSocket orchestrator
│       │   └── routes.py       ← REST: sessions, export, upload
│       ├── db/
│       │   ├── session.py      ← Async SQLAlchemy engine
│       │   └── models.py       ← Board → Session → Note schema
│       └── services/
│           └── exporter.py     ← 6-format export service
│
└── frontend/
    ├── src/
    │   ├── App.tsx             ← Root layout + source controls
    │   ├── types/index.ts      ← Shared TypeScript types
    │   ├── api/socket.ts       ← WebSocket singleton + auto-reconnect
    │   ├── hooks/useSocket.ts  ← React hook: WS state → component state
    │   └── components/
    │       ├── CanvasROI.tsx   ← Live feed + drag-to-select ROI
    │       └── LiveNotes.tsx   ← OCR panel + pages list + export grid
    └── vite.config.ts          ← Proxies /ws and /api to localhost:8000
```

---

## Configuration

All settings in `backend/app/core/config.py`, overridable via `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | localhost:5432/syncboard | Async PostgreSQL DSN |
| `OCR_ENGINE` | `tesseract` | `tesseract` or `paddle` |
| `MIN_CONFIDENCE` | `30` | Word confidence floor (0–100) |
| `CLEAR_THRESHOLD` | `0.05` | Diff fraction to trigger board-clear |
| `OCR_WIDTH` | `1280` | Frame resize width before OCR |
| `OCR_INTERVAL` | `0.8` | Seconds between OCR passes |
| `DEBOUNCE_FRAMES` | `3` | Frames of same text before TEXT_STABLE |
| `FPS_CAP` | `30` | Max stream FPS |
| `CORS_ORIGINS` | `localhost:5173` | Comma-separated allowed origins |

---

## Database Schema

```sql
boards     ( id UUID, name VARCHAR, created_at TIMESTAMPTZ )
sessions   ( id UUID, board_id FK, name VARCHAR, started_at, ended_at )
notes      ( id UUID, session_id FK, sequence_order INT,
             ocr_text TEXT, confidence FLOAT,
             image_data BYTEA, created_at TIMESTAMPTZ )
```

Tables are created automatically on first startup. No migration needed for dev.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `TesseractNotFoundError` | `brew install tesseract` then restart the backend |
| Webcam not opening | Make sure no other app is using it; try index 1 in `App.tsx` |
| OCR returns empty | Set an ROI around the board; improve lighting |
| Board-clear not triggering | Lower `CLEAR_THRESHOLD` to `0.03`; re-set reference on a truly blank board |
| Export button does nothing | Capture at least one page first — the DB session ID is set on first save |
| WebSocket disconnects | Check backend is running on :8000; check `/tmp/syncboard_backend.log` |
| `asyncpg` connection refused | Start PostgreSQL: `docker compose up postgres -d` |
| Port already in use | `start_macos.sh` will offer to kill the conflicting process |

---

## Enable PaddleOCR (optional, more accurate)

PaddleOCR handles handwriting and perspective distortion better than Tesseract but requires a ~2 GB first-run download.

```bash
# In the backend venv
pip install paddlepaddle paddleocr

# In backend/.env
OCR_ENGINE=paddle
```

---

## API Reference

Browse interactive docs at **http://localhost:8000/docs** when the backend is running.

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /api/sessions` | List all sessions |
| `GET /api/sessions/{id}` | Get session + pages |
| `DELETE /api/sessions/{id}` | Delete a session |
| `GET /api/sessions/{id}/export/{fmt}` | Download export (fmt = pdf/docx/pptx/markdown/txt/json) |
| `POST /api/upload` | Upload video or image files |
| `WS /ws` | Main WebSocket endpoint |
