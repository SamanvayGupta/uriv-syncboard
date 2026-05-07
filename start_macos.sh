#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  SyncBoard — macOS Startup Script
#
#  Architecture:
#    PostgreSQL  → Docker container  (port 5432)
#    Backend     → local Python      (port 8000) ← needs local for webcam
#    Frontend    → local Node/Vite   (port 5173)
#
#  Prerequisites (run once):
#    brew install tesseract
#    brew install --cask docker     # Docker Desktop
#
#  Usage:
#    chmod +x start_macos.sh && ./start_macos.sh
# ══════════════════════════════════════════════════════════════

set -e

# ── Colours ───────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1m'; NC='\033[0m'
info()  { echo -e "${G}▶  $*${NC}"; }
warn()  { echo -e "${Y}⚠  $*${NC}"; }
err()   { echo -e "${R}✗  $*${NC}"; exit 1; }
step()  { echo -e "\n${B}── $* ──${NC}"; }

echo ""
echo -e "${B}╔═══════════════════════════════════════════╗${NC}"
echo -e "${B}║   SyncBoard  •  macOS Startup             ║${NC}"
echo -e "${B}╚═══════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────
step "Checking prerequisites"
# ─────────────────────────────────────────────────────────────

command -v python3 &>/dev/null || err "Python 3 not found.\n  Fix: brew install python"
command -v node    &>/dev/null || err "Node.js not found.\n  Fix: brew install node"

PY=$(command -v python3)
info "Python  $($PY --version)"
info "Node    $(node --version)"
info "npm     $(npm --version)"

if command -v tesseract &>/dev/null; then
    info "Tesseract $(tesseract --version 2>&1 | head -1)"
else
    echo ""
    warn "Tesseract not installed — OCR will not work."
    echo -e "  ${B}Fix:${NC}  brew install tesseract"
    echo ""
    read -rp "  Continue without OCR? (y/N) " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0
fi

# ─────────────────────────────────────────────────────────────
step "Checking port availability"
# ─────────────────────────────────────────────────────────────

for PORT in 8000 5173; do
    if lsof -i ":$PORT" &>/dev/null 2>&1; then
        PROC=$(lsof -i ":$PORT" | tail -1 | awk '{print $1, $2}')
        warn "Port $PORT is in use by: $PROC"
        read -rp "  Kill it and continue? (y/N) " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true
            sleep 1
            info "Port $PORT freed."
        else
            err "Cannot start on port $PORT"
        fi
    else
        info "Port $PORT free ✓"
    fi
done

# ─────────────────────────────────────────────────────────────
step "Starting PostgreSQL (Docker)"
# ─────────────────────────────────────────────────────────────

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    info "Starting postgres container…"
    docker compose up postgres -d 2>/dev/null || true
    info "Waiting for PostgreSQL…"
    for i in $(seq 1 20); do
        if docker compose exec -T postgres pg_isready -U syncboard &>/dev/null 2>&1; then
            info "PostgreSQL ready ✓"; break
        fi
        sleep 1
        [[ $i -eq 20 ]] && warn "PostgreSQL slow to start — continuing anyway"
    done
else
    warn "Docker not running — skipping PostgreSQL."
    warn "Session data won't be persisted (exports will still work in-memory)."
fi

# ─────────────────────────────────────────────────────────────
step "Setting up Python virtual environment"
# ─────────────────────────────────────────────────────────────

cd "$(dirname "$0")/backend"

if [[ ! -d .venv ]]; then
    info "Creating virtual environment…"
    $PY -m venv .venv
fi
source .venv/bin/activate
info "venv activated: $VIRTUAL_ENV"

info "Installing Python dependencies (first run ~60s)…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
info "Python deps ready ✓"

# ─────────────────────────────────────────────────────────────
step "Writing backend/.env"
# ─────────────────────────────────────────────────────────────

if [[ ! -f .env ]]; then
    cat > .env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard
OCR_ENGINE=tesseract
MIN_CONFIDENCE=30
CLEAR_THRESHOLD=0.05
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173
ENVEOF
    info "Created backend/.env"
else
    info "backend/.env exists — using it"
fi

# ─────────────────────────────────────────────────────────────
step "Starting FastAPI backend on :8000"
# ─────────────────────────────────────────────────────────────

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info \
    > /tmp/syncboard_backend.log 2>&1 &
BACKEND_PID=$!

info "Backend PID $BACKEND_PID — waiting for startup…"
for i in $(seq 1 25); do
    if curl -sf http://localhost:8000/health &>/dev/null; then
        info "Backend ready ✓  →  http://localhost:8000"; break
    fi
    sleep 1
    [[ $i -eq 25 ]] && {
        warn "Backend didn't respond. Last 20 log lines:"
        tail -20 /tmp/syncboard_backend.log
        err "Backend failed to start. Check /tmp/syncboard_backend.log"
    }
done

cd ..

# ─────────────────────────────────────────────────────────────
step "Setting up frontend"
# ─────────────────────────────────────────────────────────────

cd frontend

if [[ ! -d node_modules ]]; then
    info "Installing npm packages (first run ~30s)…"
    npm install
else
    info "node_modules present ✓"
fi

info "Starting Vite dev server on :5173…"
npm run dev > /tmp/syncboard_frontend.log 2>&1 &
FRONTEND_PID=$!

for i in $(seq 1 20); do
    if curl -sf http://localhost:5173 &>/dev/null; then
        info "Frontend ready ✓  →  http://localhost:5173"; break
    fi
    sleep 1
    [[ $i -eq 20 ]] && warn "Frontend slow — check /tmp/syncboard_frontend.log"
done

cd ..

# ─────────────────────────────────────────────────────────────
# FIX: auto-open browser
sleep 0.5
open "http://localhost:5173" 2>/dev/null || true
# ─────────────────────────────────────────────────────────────

echo ""
echo -e "${G}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${G}║  🎉  SyncBoard is running!                       ║${NC}"
echo -e "${G}║                                                  ║${NC}"
echo -e "${G}║  App     →  http://localhost:5173               ║${NC}"
echo -e "${G}║  API     →  http://localhost:8000               ║${NC}"
echo -e "${G}║  Docs    →  http://localhost:8000/docs          ║${NC}"
echo -e "${G}║                                                  ║${NC}"
echo -e "${G}║  Logs:                                          ║${NC}"
echo -e "${G}║    tail -f /tmp/syncboard_backend.log            ║${NC}"
echo -e "${G}║    tail -f /tmp/syncboard_frontend.log           ║${NC}"
echo -e "${G}║                                                  ║${NC}"
echo -e "${G}║  Press Ctrl+C to stop all services              ║${NC}"
echo -e "${G}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────
trap "
  echo ''
  info 'Stopping SyncBoard…'
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  docker compose stop postgres 2>/dev/null || true
  info 'All services stopped.'
" EXIT INT TERM

wait $BACKEND_PID $FRONTEND_PID
