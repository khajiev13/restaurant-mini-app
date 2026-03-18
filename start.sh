#!/usr/bin/env bash
# start.sh — Start Docker containers + jprq tunnels
# Usage: ./start.sh [--rebuild]

set -euo pipefail

BACKEND_PORT=8001
FRONTEND_PORT=3001
BACKEND_SUBDOMAIN=olot-somsa-api
FRONTEND_SUBDOMAIN=olot-somsa
BACKEND_URL="https://${BACKEND_SUBDOMAIN}.jprq.live"
FRONTEND_URL="https://${FRONTEND_SUBDOMAIN}.jprq.live"
JPRQ_BACKEND_LOG=/tmp/jprq_backend.log
JPRQ_FRONTEND_LOG=/tmp/jprq_frontend.log

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Preflight ───────────────────────────────────────────────────────────────
command -v docker   >/dev/null 2>&1 || die "docker not found. Install Docker Desktop."
command -v jprq >/dev/null 2>&1 || die "jprq not found. See https://jprq.io"
[ -f .env ] || die ".env file not found. Copy .env.example → .env and fill in your values."

# ── Docker ──────────────────────────────────────────────────────────────────
REBUILD_FLAG=""
if [[ "${1:-}" == "--rebuild" ]]; then
  REBUILD_FLAG="--build"
  info "Rebuilding Docker images..."
fi

info "Starting Docker containers..."
docker compose up -d $REBUILD_FLAG

info "Waiting for containers to be healthy..."
for i in $(seq 1 30); do
  STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
lines = sys.stdin.read().strip().splitlines()
states = [json.loads(l).get('State','') for l in lines if l.strip()]
print('ok' if all(s in ('running','healthy') for s in states) else 'wait')
" 2>/dev/null || echo "wait")
  [ "$STATUS" = "ok" ] && break
  sleep 2
done
info "Containers running."

# ── Kill stale tunnels ───────────────────────────────────────────────────────
pkill -f "jprq http" 2>/dev/null || true
sleep 1

# ── Backend tunnel ───────────────────────────────────────────────────────────
info "Starting backend tunnel → ${BACKEND_URL}"
> "$JPRQ_BACKEND_LOG"
jprq http ${BACKEND_PORT} -s ${BACKEND_SUBDOMAIN} 2>&1 | tee "$JPRQ_BACKEND_LOG" &

# ── Frontend tunnel ──────────────────────────────────────────────────────────
info "Starting frontend tunnel → ${FRONTEND_URL}"
> "$JPRQ_FRONTEND_LOG"
jprq http ${FRONTEND_PORT} -s ${FRONTEND_SUBDOMAIN} 2>&1 | tee "$JPRQ_FRONTEND_LOG" &

sleep 3

# ── Update .env with backend URL (only if changed) ───────────────────────────
CURRENT_URL=$(grep "^VITE_API_BASE_URL=" .env | cut -d= -f2- || true)
if [ "$CURRENT_URL" != "$BACKEND_URL" ]; then
  info "Setting VITE_API_BASE_URL=${BACKEND_URL} in .env"
  if grep -q "^VITE_API_BASE_URL=" .env; then
    sed -i '' "s|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=${BACKEND_URL}|" .env
  else
    echo "VITE_API_BASE_URL=${BACKEND_URL}" >> .env
  fi
  info "Rebuilding frontend container with new API URL..."
  docker compose up -d --build --no-deps frontend >/dev/null 2>&1
else
  info "VITE_API_BASE_URL unchanged, skipping frontend rebuild."
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅  All services running!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  🖥  Frontend  →  ${YELLOW}${FRONTEND_URL}${NC}"
echo -e "  🔧  Backend   →  ${YELLOW}${BACKEND_URL}${NC}"
echo ""
echo -e "  📱  Set this URL in BotFather:"
echo -e "      ${GREEN}${FRONTEND_URL}${NC}"
echo ""
echo -e "  📋  BotFather commands (one-time setup):"
echo -e "      /setmenubutton → choose your bot → ${FRONTEND_URL}"
echo -e "      or: /newapp → choose bot → set Web App URL to above"
echo ""
echo -e "${GREEN}  ✅  URLs are permanent — no need to update BotFather again!${NC}"
echo ""
