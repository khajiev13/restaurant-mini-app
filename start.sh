#!/usr/bin/env bash
# start.sh — Start Docker containers + Cloudflare named tunnel
# Usage: ./start.sh [--rebuild]

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

require_env() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- | sed -E 's/^"(.*)"$/\1/' || true)"
  [ -n "$value" ] || die "${key} is missing from .env"
  printf '%s' "$value"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $0 ~ ("^" key "=") {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' .env > "$tmp_file"

  mv "$tmp_file" .env
}

telegram_api_json() {
  local method="$1"
  local payload="$2"
  curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}" \
    -H 'Content-Type: application/json' \
    -d "$payload"
}

telegram_api_form() {
  local method="$1"
  shift
  curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}" "$@"
}

command -v docker >/dev/null 2>&1 || die "docker not found. Install Docker Desktop."
[ -f .env ] || die ".env file not found. Copy .env.example → .env and fill in your values."

TELEGRAM_BOT_TOKEN="$(require_env TELEGRAM_BOT_TOKEN)"
TELEGRAM_WEBHOOK_SECRET="$(require_env TELEGRAM_WEBHOOK_SECRET)"
PUBLIC_APP_URL_CONFIGURED="$(require_env PUBLIC_APP_URL)"
CLOUDFLARE_TUNNEL_TOKEN_CONFIGURED="$(require_env CLOUDFLARE_TUNNEL_TOKEN)"

REBUILD_FLAG=""
if [[ "${1:-}" == "--rebuild" ]]; then
  REBUILD_FLAG="--build"
  info "Rebuilding Docker images..."
fi

info "Removing stale tunnel containers..."
docker rm -f restaurant_cloudflared >/dev/null 2>&1 || true

info "Starting Docker containers..."
docker compose up -d $REBUILD_FLAG postgres backend frontend caddy cloudflared

info "Waiting for core containers to be healthy..."
for _ in $(seq 1 30); do
  STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
lines = sys.stdin.read().strip().splitlines()
states = [json.loads(line).get('State', '') for line in lines if line.strip()]
print('ok' if all(state in ('running', 'healthy') for state in states) else 'wait')
" 2>/dev/null || echo "wait")
  [ "$STATUS" = "ok" ] && break
  sleep 2
done

info "Verifying the local origin through Caddy..."
curl -fsS "http://127.0.0.1:8080/healthz" >/dev/null || die "Caddy is not reachable on localhost:8080."
curl -fsS "http://127.0.0.1:8080/api/health" >/dev/null || die "Backend API is not healthy behind Caddy."

info "Restarting Cloudflare named tunnel..."
docker compose up -d --force-recreate --no-deps cloudflared >/dev/null

PUBLIC_URL="${PUBLIC_APP_URL_CONFIGURED%/}"
info "Waiting for stable hostname ${PUBLIC_URL}..."
for _ in $(seq 1 90); do
  if curl -fsS "${PUBLIC_URL}/" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "${PUBLIC_URL}/" >/dev/null || die "Stable hostname ${PUBLIC_URL} is not reachable. Check Cloudflare DNS and tunnel public hostname."

set_env_value "PUBLIC_APP_URL" "${PUBLIC_URL}"
set_env_value "VITE_API_BASE_URL" ""

info "Verifying the public app and API..."
curl -fsS "${PUBLIC_URL}/healthz" >/dev/null
curl -fsS "${PUBLIC_URL}/api/health" >/dev/null

info "Updating Telegram webhook..."
telegram_api_form setWebhook \
  --data-urlencode "url=${PUBLIC_URL}/api/webhooks/bot" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode "allowed_updates=[\"message\"]" >/dev/null

info "Updating Telegram menu button..."
MENU_PAYLOAD=$(cat <<JSON
{"menu_button":{"type":"web_app","text":"Open Menu","web_app":{"url":"${PUBLIC_URL}/"}}}
JSON
)
telegram_api_json setChatMenuButton "${MENU_PAYLOAD}" >/dev/null

WEBHOOK_INFO="$(telegram_api_form getWebhookInfo)"
MENU_INFO="$(telegram_api_form getChatMenuButton)"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅  App exposed through Cloudflare named tunnel${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  🌍  Public app     →  ${YELLOW}${PUBLIC_URL}/${NC}"
echo -e "  🔗  Webhook        →  ${YELLOW}${PUBLIC_URL}/api/webhooks/bot${NC}"
echo ""
echo -e "  🤖  Telegram webhook info:"
echo "      ${WEBHOOK_INFO}"
echo ""
echo -e "  📱  Telegram menu button:"
echo "      ${MENU_INFO}"
echo ""
info "Named tunnel mode uses a stable hostname."
