#!/usr/bin/env bash
# start.sh — Start Docker containers + Cloudflare tunnels for local development
# Usage: ./start.sh [--rebuild]

set -euo pipefail

BACKEND_PORT=8001
FRONTEND_PORT=3001
CF_BACKEND_LOG=/tmp/cf_backend.log
CF_FRONTEND_LOG=/tmp/cf_frontend.log

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Preflight ───────────────────────────────────────────────────────────────
command -v docker   >/dev/null 2>&1 || die "docker not found. Install Docker Desktop."
command -v cloudflared >/dev/null 2>&1 || die "cloudflared not found. Run: brew install cloudflared"
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
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

# ── Backend tunnel ───────────────────────────────────────────────────────────
info "Starting backend tunnel (localhost:${BACKEND_PORT})..."
> "$CF_BACKEND_LOG"
cloudflared tunnel --url "http://localhost:${BACKEND_PORT}" --no-autoupdate 2>&1 | tee "$CF_BACKEND_LOG" &

BACKEND_URL=""
for i in $(seq 1 20); do
  BACKEND_URL=$(grep -o 'https://[^ ]*trycloudflare\.com' "$CF_BACKEND_LOG" 2>/dev/null | head -1 || true)
  [ -n "$BACKEND_URL" ] && break
  sleep 1
done
[ -n "$BACKEND_URL" ] || die "Backend tunnel failed to start. Check $CF_BACKEND_LOG"

# ── Frontend tunnel ──────────────────────────────────────────────────────────
info "Starting frontend tunnel (localhost:${FRONTEND_PORT})..."
> "$CF_FRONTEND_LOG"
cloudflared tunnel --url "http://localhost:${FRONTEND_PORT}" --no-autoupdate 2>&1 | tee "$CF_FRONTEND_LOG" &

FRONTEND_URL=""
for i in $(seq 1 20); do
  FRONTEND_URL=$(grep -o 'https://[^ ]*trycloudflare\.com' "$CF_FRONTEND_LOG" 2>/dev/null | head -1 || true)
  [ -n "$FRONTEND_URL" ] && break
  sleep 1
done
[ -n "$FRONTEND_URL" ] || die "Frontend tunnel failed to start. Check $CF_FRONTEND_LOG"

# ── Update .env with new backend URL ────────────────────────────────────────
info "Updating VITE_API_BASE_URL in .env → ${BACKEND_URL}"
if grep -q "^VITE_API_BASE_URL=" .env; then
  sed -i '' "s|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=${BACKEND_URL}|" .env
else
  echo "VITE_API_BASE_URL=${BACKEND_URL}" >> .env
fi

# ── Rebuild frontend with new backend URL ────────────────────────────────────
info "Rebuilding frontend container with new API URL..."
docker compose up -d --build --no-deps frontend >/dev/null 2>&1

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
echo -e "  📋  BotFather commands:"
echo -e "      /setmenubutton → choose your bot → ${FRONTEND_URL}"
echo -e "      or: /newapp → choose bot → set Web App URL to above"
echo ""
echo -e "${YELLOW}  ⚠  Tunnel URLs change every restart — update BotFather each time.${NC}"
echo ""
