#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  SyncBoard — Local Development Startup
#  Starts PostgreSQL (Docker), Backend, and Frontend.
#  No Docker needed for backend/frontend.
#
#  Usage:  chmod +x start_local.sh && ./start_local.sh
# ══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${GREEN}[SyncBoard]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 1. Check Python ───────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  error "Python 3 not found. Install from https://python.org"
fi
PYTHON=$(command -v python3)
info "Using Python: $($PYTHON --version)"

# ── 2. Check Tesseract ────────────────────────────────────────
if ! command -v tesseract &>/dev/null; then
  warn "Tesseract OCR not found."
  echo ""
  echo "  Install it:"
  echo "    macOS  : brew install tesseract"
  echo "    Ubuntu : sudo apt install tesseract-ocr"
  echo "    Windows: https://github.com/UB-Mannheim/tesseract/wiki"
  echo ""
  read -rp "  Continue without OCR? (y/N) " yn
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
else
  info "Tesseract found: $(tesseract --version 2>&1 | head -1)"
fi

# ── 3. Check Node ─────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  error "Node.js not found. Install from https://nodejs.org"
fi
info "Using Node: $(node --version)"

# ── 4. Start PostgreSQL via Docker (just the DB) ──────────────
if command -v docker &>/dev/null; then
  info "Starting PostgreSQL container…"
  docker compose up postgres -d 2>/dev/null || warn "Docker not available — skipping DB."
  sleep 2
else
  warn "Docker not found — skipping PostgreSQL. Backend will log DB errors but still work."
fi

# ── 5. Install backend dependencies ──────────────────────────
info "Installing backend Python dependencies…"
cd backend
if [ ! -d ".venv" ]; then
  $PYTHON -m venv .venv
fi
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
info "Backend dependencies installed."

# ── 6. Write local .env ───────────────────────────────────────
if [ ! -f ".env" ]; then
  cat > .env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard
OCR_ENGINE=tesseract
MIN_CONFIDENCE=30
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173
ENVEOF
  info "Created backend/.env"
fi

# ── 7. Start backend ──────────────────────────────────────────
info "Starting FastAPI backend on http://localhost:8000 …"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

sleep 2

# ── 8. Install frontend dependencies ─────────────────────────
info "Installing frontend Node dependencies…"
cd frontend
npm install --silent
info "Frontend dependencies installed."

# ── 9. Start frontend ─────────────────────────────────────────
info "Starting Vite dev server on http://localhost:5173 …"
npm run dev &
FRONTEND_PID=$!
cd ..

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  SyncBoard is running!${NC}"
echo -e "${GREEN}  Frontend : http://localhost:5173${NC}"
echo -e "${GREEN}  Backend  : http://localhost:8000${NC}"
echo -e "${GREEN}  API docs : http://localhost:8000/docs${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo "  Press Ctrl+C to stop all services."
echo ""

# ── Cleanup on exit ───────────────────────────────────────────
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; info 'Stopped.'" EXIT INT TERM
wait
