# Home Host Clean Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the exact latest `origin/prod` restaurant Mini App to SSH host
`home` with a fresh PostgreSQL volume and make `home` the active public tunnel
connector.

**Architecture:** Preserve the stopped `home` deployment as timestamped recovery
material, remove only its restaurant Compose resources, and clone the pinned
production candidate into the canonical application path. Initialize PostgreSQL
from `database/init.sql`, build and start the restaurant services in dependency
order, then register the existing public hostname and Telegram integration from
`home`. Isolate the old `restaurant` connector if that host becomes reachable.

**Tech Stack:** Git, GitHub Actions, SSH, Ubuntu 24.04, Docker 28, Docker Compose
2.35, PostgreSQL 16, FastAPI, React/Vite, Caddy, Cloudflare Tunnel, Telegram Bot
API.

## Global Constraints

- Approved production candidate: `cbd82133d4a00dc545e611bb04bd07519509454d`.
- Deployment host: SSH alias `home`, Linux user `khajiev13`.
- Canonical remote path: `/home/khajiev13/apps/restaurant-mini-app`.
- PostgreSQL starts from a new named volume; no prior rows are restored.
- Preserve the old source, `.env`, and PostgreSQL files in a timestamped,
  user-readable-only archive before removing the old volume.
- Never print `.env` values, tokens, provider payloads, authorization headers,
  customer data, or business identifiers.
- Reuse existing AliPOS, Multicard, Telegram, Cloudflare, Yandex, PostgreSQL,
  and JWT configuration values from `home`.
- Set a separate random `TABLE_ACCESS_SECRET` if it is absent.
- Keep `INPLACE_ONLINE_PAYMENT_ENABLED=true`, matching the approved production
  table-payment rollout.
- Do not modify or start BitAgent resources on `home`.
- Do not use `docker system prune`, `docker volume prune`, broad process
  listings, force-pushes, or recursive deletion of a variable-derived path.
- The old `restaurant` host is currently unreachable. Its tunnel isolation is a
  required retry, but continued unreachability does not block a healthy `home`
  deployment if the residual reconnection risk is reported.

---

### Task 1: Pin and validate the production release

**Files:**
- Reference: `docs/superpowers/specs/2026-07-19-home-host-clean-cutover-design.md`
- Reference: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: current `origin/prod` and its GitHub Actions result.
- Produces: exact candidate SHA `cbd82133d4a00dc545e611bb04bd07519509454d`
  approved for deployment.

- [ ] **Step 1: Refresh remote refs locally**

Run:

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
git fetch --prune origin
git rev-parse origin/prod
```

Expected: the final line is
`cbd82133d4a00dc545e611bb04bd07519509454d`. Stop and revise the plan if the
remote tip changed.

- [ ] **Step 2: Verify exact-SHA CI**

Run:

```bash
gh run list \
  --repo khajiev13/restaurant-mini-app \
  --commit cbd82133d4a00dc545e611bb04bd07519509454d \
  --json headSha,status,conclusion,workflowName,url \
  --limit 10
```

Expected: the `CI` workflow for the exact candidate has `status=completed` and
`conclusion=success`. If it is queued, wait for it. If it failed or is absent,
stop before changing `home`.

- [ ] **Step 3: Capture secret-safe `home` and BitAgent baselines**

Run:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 home '
printf "host="; hostname
printf "docker="; docker --version
printf "compose="; docker compose version
printf "disk="; df -h /home/khajiev13/apps | tail -n 1
printf "restaurant="
docker ps -a --filter name=restaurant_ \
  --format "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
printf "bitagent="
docker ps -a --filter name=lab4_professor_ \
  --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}"
'
```

Expected: Docker and Compose respond, sufficient disk space remains, the five
restaurant containers are stopped, and the BitAgent baseline is recorded
without environment values.

---

### Task 2: Archive the stopped `home` deployment

**Files:**
- Archive: the validated directory stored in
  `/tmp/restaurant-home-cutover-root`
- Source: `/home/khajiev13/apps/restaurant-mini-app/.env`
- Source volume: `restaurant-mini-app_pgdata`

**Interfaces:**
- Consumes: stopped legacy checkout, protected `.env`, and old PostgreSQL
  volume.
- Produces: validated timestamped recovery archive and exact archive path in
  `/tmp/restaurant-home-cutover-root`.

- [ ] **Step 1: Allocate and validate the recovery path**

Run on `home`:

```bash
cutover_id="$(date -u +%Y%m%dT%H%M%SZ)"
cutover_root="/home/khajiev13/apps/.restaurant-home-cutover-${cutover_id}"
case "$cutover_root" in
  /home/khajiev13/apps/.restaurant-home-cutover-20??????T??????Z) ;;
  *) echo "invalid cutover path" >&2; exit 1 ;;
esac
install -d -m 700 "$cutover_root"
printf '%s\n' "$cutover_root" > /tmp/restaurant-home-cutover-root
test -d "$cutover_root"
test "$(stat -c %a "$cutover_root")" = 700
```

Expected: one new mode-700 directory under `/home/khajiev13/apps`, and the
validated absolute path is stored in `/tmp/restaurant-home-cutover-root`.

- [ ] **Step 2: Preserve source state and protected configuration**

Run on `home`:

```bash
cutover_root="$(sed -n '1p' /tmp/restaurant-home-cutover-root)"
test -d "$cutover_root"
cd /home/khajiev13/apps/restaurant-mini-app
git rev-parse HEAD > "$cutover_root/legacy-source-sha.txt"
git status --short > "$cutover_root/legacy-source-status.txt"
git diff --binary > "$cutover_root/legacy-source-tracked.patch"
install -m 600 .env "$cutover_root/restaurant.env"
docker ps -a --filter name=restaurant_ \
  --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}" \
  > "$cutover_root/legacy-containers.txt"
test "$(stat -c %a "$cutover_root/restaurant.env")" = 600
```

Expected: the archive contains the old SHA, source status, tracked patch,
container identities, and a mode-600 `.env` copy. No file contents are printed.

- [ ] **Step 3: Archive the stopped PostgreSQL volume**

Run on `home`:

```bash
cutover_root="$(sed -n '1p' /tmp/restaurant-home-cutover-root)"
test -d "$cutover_root"
docker inspect -f '{{.State.Status}}' restaurant_postgres | grep -Fx exited
docker run --rm --network none \
  --mount type=volume,src=restaurant-mini-app_pgdata,dst=/source,readonly \
  --mount type=bind,src="$cutover_root",dst=/backup \
  postgres:16 \
  tar -C /source -czf /backup/legacy-pgdata.tgz .
test -s "$cutover_root/legacy-pgdata.tgz"
gzip -t "$cutover_root/legacy-pgdata.tgz"
chmod 600 "$cutover_root/legacy-pgdata.tgz"
```

Expected: the legacy database archive is non-empty, passes `gzip -t`, and is
mode 600.

---

### Task 3: Replace the old checkout and data volume

**Files:**
- Move: `/home/khajiev13/apps/restaurant-mini-app`
- Create: `/home/khajiev13/apps/restaurant-mini-app`
- Restore: `/home/khajiev13/apps/restaurant-mini-app/.env`

**Interfaces:**
- Consumes: validated recovery archive and exact production candidate.
- Produces: clean detached candidate checkout, protected configuration, and no
  legacy restaurant containers or volumes.

- [ ] **Step 1: Remove only the legacy restaurant Compose resources**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
docker compose down --volumes --remove-orphans
test -z "$(docker ps -aq --filter name=restaurant_)"
test -z "$(docker volume ls -q --filter name=restaurant-mini-app_)"
docker ps -a --filter name=lab4_professor_ \
  --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}"
```

Expected: no `restaurant_` containers or `restaurant-mini-app_` volumes remain,
while BitAgent identifiers and status match Task 1.

- [ ] **Step 2: Move the legacy source into its archive**

Run on `home`:

```bash
cutover_root="$(sed -n '1p' /tmp/restaurant-home-cutover-root)"
test -d "$cutover_root"
test -d /home/khajiev13/apps/restaurant-mini-app/.git
mv /home/khajiev13/apps/restaurant-mini-app "$cutover_root/legacy-source"
test -d "$cutover_root/legacy-source/.git"
test ! -e /home/khajiev13/apps/restaurant-mini-app
```

Expected: the canonical path is free and the complete legacy source is inside
the protected recovery directory.

- [ ] **Step 3: Clone and pin the production candidate**

Run on `home`:

```bash
git clone --branch prod --single-branch \
  https://github.com/khajiev13/restaurant-mini-app.git \
  /home/khajiev13/apps/restaurant-mini-app
cd /home/khajiev13/apps/restaurant-mini-app
git checkout --detach cbd82133d4a00dc545e611bb04bd07519509454d
test "$(git rev-parse HEAD)" = cbd82133d4a00dc545e611bb04bd07519509454d
test -z "$(git status --porcelain)"
```

Expected: clean detached `HEAD` exactly equals the approved SHA.

- [ ] **Step 4: Restore and validate configuration without printing values**

Run on `home`:

```bash
cutover_root="$(sed -n '1p' /tmp/restaurant-home-cutover-root)"
install -m 600 "$cutover_root/restaurant.env" \
  /home/khajiev13/apps/restaurant-mini-app/.env
cd /home/khajiev13/apps/restaurant-mini-app
for key in \
  TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET PUBLIC_APP_URL \
  CLOUDFLARE_TUNNEL_TOKEN ALIPOS_API_CLIENT_ID \
  ALIPOS_API_CLIENT_SECRET ALIPOS_RESTAURANT_ID POSTGRES_USER \
  POSTGRES_PASSWORD POSTGRES_DB JWT_SECRET MULTICARD_API_BASE_URL \
  MULTICARD_APPLICATION_ID MULTICARD_SECRET MULTICARD_STORE_ID \
  YANDEX_MAPS_API_KEY YANDEX_GEOSUGGEST_API_KEY
do
  grep -Eq "^${key}=.+" .env || { echo "missing_config_key=${key}"; exit 1; }
done
test "$(stat -c %a .env)" = 600
```

Expected: all named keys are non-empty and only missing key names could be
printed.

- [ ] **Step 5: Add the application-owned table secret and enable table payments**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
if ! grep -Eq '^TABLE_ACCESS_SECRET=.+' .env; then
  table_access_secret="$(openssl rand -hex 32)"
  printf 'TABLE_ACCESS_SECRET=%s\n' "$table_access_secret" >> .env
  unset table_access_secret
fi
if grep -q '^INPLACE_ONLINE_PAYMENT_ENABLED=' .env; then
  sed -i 's/^INPLACE_ONLINE_PAYMENT_ENABLED=.*/INPLACE_ONLINE_PAYMENT_ENABLED=true/' .env
else
  printf '%s\n' 'INPLACE_ONLINE_PAYMENT_ENABLED=true' >> .env
fi
chmod 600 .env
docker compose config --quiet
```

Expected: Compose configuration validates without printing its resolved secret
values.

---

### Task 4: Build and initialize the clean stack

**Files:**
- Build: `/home/khajiev13/apps/restaurant-mini-app/backend/Dockerfile`
- Build: `/home/khajiev13/apps/restaurant-mini-app/frontend/Dockerfile`
- Initialize: `/home/khajiev13/apps/restaurant-mini-app/database/init.sql`

**Interfaces:**
- Consumes: clean exact-SHA checkout and validated `.env`.
- Produces: fresh PostgreSQL schema and healthy backend, frontend, and Caddy
  containers before the public connector starts.

- [ ] **Step 1: Build the application images**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
docker compose build backend frontend
```

Expected: both builds exit zero. If dependency downloads fail only inside the
Docker build while host DNS works, run this exact fallback on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
yandex_maps_key="$(sed -n 's/^YANDEX_MAPS_API_KEY=//p' .env | tail -n 1)"
docker build --network host \
  -t restaurant-mini-app-backend:latest ./backend
docker build --network host \
  --build-arg VITE_API_BASE_URL= \
  --build-arg VITE_YANDEX_MAPS_API_KEY="$yandex_maps_key" \
  -t restaurant-mini-app-frontend:latest ./frontend
unset yandex_maps_key
```

Do not change daemon-wide DNS.

- [ ] **Step 2: Start only fresh PostgreSQL**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
docker compose up -d postgres
for attempt in $(seq 1 30); do
  state="$(docker inspect -f '{{.State.Health.Status}}' restaurant_postgres)"
  test "$state" = healthy && break
  sleep 2
done
test "$(docker inspect -f '{{.State.Health.Status}}' restaurant_postgres)" = healthy
docker volume inspect restaurant-mini-app_pgdata \
  --format '{{.Name}}|{{.CreatedAt}}'
```

Expected: a newly created `restaurant-mini-app_pgdata` exists and PostgreSQL is
healthy.

- [ ] **Step 3: Verify the initialized schema is current and empty**

Run on `home`:

```bash
docker exec restaurant_postgres sh -lc '
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
"SELECT string_agg(tablename, '\''|'\'' ORDER BY tablename)
 FROM pg_tables
 WHERE schemaname='\''public'\'';" |
grep -Fx "addresses|orders|stoplist|users"
'
docker exec restaurant_postgres sh -lc '
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
"SELECT (SELECT count(*) FROM users)::text || '\''|'\'' ||
        (SELECT count(*) FROM orders)::text;" |
grep -Fx "0|0"
'
docker exec restaurant_postgres sh -lc '
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
"SELECT count(*) FROM information_schema.columns
 WHERE table_schema='\''public'\''
   AND ((table_name='\''users'\'' AND column_name IN
          ('\''phone_verified_at'\'', '\''phone_verified_fingerprint'\'',
           '\''phone_verified_message_at'\'', '\''phone_verified_update_id'\''))
     OR (table_name='\''orders'\'' AND column_name='\''contact_phone_verified'\''));" |
grep -Fx "5"
'
```

Expected: four expected tables, zero users/orders, and all five verified-phone
columns.

- [ ] **Step 4: Start the private application origin**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
docker compose up -d backend frontend caddy
for attempt in $(seq 1 45); do
  unhealthy="$(docker inspect -f '{{.Name}}={{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    restaurant_postgres restaurant_backend restaurant_frontend restaurant_caddy |
    grep -Ev '=healthy$' || true)"
  test -z "$unhealthy" && break
  sleep 2
done
test -z "$(docker inspect -f '{{.Name}}={{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
  restaurant_postgres restaurant_backend restaurant_frontend restaurant_caddy |
  grep -Ev '=healthy$' || true)"
curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsS http://127.0.0.1:8080/api/health >/dev/null
```

Expected: all four private-origin containers are healthy and both local routes
return HTTP 200.

---

### Task 5: Activate public traffic and Telegram

**Files:**
- Execute: `/home/khajiev13/apps/restaurant-mini-app/start.sh`

**Interfaces:**
- Consumes: healthy private application origin and existing tunnel/bot
  credentials.
- Produces: active `home` Cloudflare connector, current Telegram webhook, and
  current Telegram menu button.

- [ ] **Step 1: Run the repository activation script**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
./start.sh
```

Expected: the script verifies local/public application health, registers the
webhook, verifies the Telegram menu button, and exits zero without printing any
token.

- [ ] **Step 2: Verify local and public health explicitly**

Run on `home`:

```bash
for url in \
  http://127.0.0.1:8080/healthz \
  http://127.0.0.1:8080/api/health \
  https://restaurant.labtutor.app/healthz \
  https://restaurant.labtutor.app/api/health
do
  code="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$url")"
  printf '%s|%s\n' "$url" "$code"
  test "$code" = 200
done
```

Expected: all four routes return HTTP 200.

- [ ] **Step 3: Verify sanitized Telegram state**

Run on `home`:

```bash
docker exec restaurant_backend python -c '
import asyncio
import os
import httpx

async def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=10) as client:
        webhook = (await client.get(f"{base}/getWebhookInfo")).json()
        menu = (await client.get(f"{base}/getChatMenuButton")).json()
    result = webhook.get("result") or {}
    button = menu.get("result") or {}
    print(
        "webhook_ok=%s|url_match=%s|pending=%s|last_error=%s"
        % (
            webhook.get("ok") is True,
            result.get("url")
            == "https://restaurant.labtutor.app/api/webhooks/bot",
            result.get("pending_update_count", -1),
            bool(result.get("last_error_message")),
        )
    )
    print(
        "menu_ok=%s|url_match=%s"
        % (
            menu.get("ok") is True,
            (button.get("web_app") or {}).get("url")
            == "https://restaurant.labtutor.app/",
        )
    )

asyncio.run(main())
'
```

Expected:

```text
webhook_ok=True|url_match=True|pending=0|last_error=False
menu_ok=True|url_match=True
```

---

### Task 6: Prove stability and isolate the old connector

**Files:**
- Evidence: `acceptance.txt` below the validated directory stored in
  `/tmp/restaurant-home-cutover-root`
- Conditional old-host configuration:
  `/home/khajiev13/apps/restaurant-mini-app/.env` on SSH host `restaurant`

**Interfaces:**
- Consumes: active public deployment on `home`.
- Produces: exact-SHA/container acceptance evidence and disabled old tunnel
  credentials when `restaurant` is reachable.

- [ ] **Step 1: Capture exact source, image, health, restart, and error evidence**

Run on `home`:

```bash
cutover_root="$(sed -n '1p' /tmp/restaurant-home-cutover-root)"
cd /home/khajiev13/apps/restaurant-mini-app
{
  printf 'source_sha='; git rev-parse HEAD
  docker compose ps --format '{{.Name}}|{{.Image}}|{{.State}}|{{.Status}}'
  docker inspect -f '{{.Name}}|restart={{.RestartCount}}|image={{.Image}}' \
    restaurant_postgres restaurant_backend restaurant_frontend \
    restaurant_caddy restaurant_cloudflared
  printf 'backend_error_markers='
  docker logs --since 15m --tail 500 restaurant_backend 2>&1 |
    grep -Eic 'traceback|critical|startup failed|database.*error|telegram.*failed|alipos.*error|multicard.*error' || true
} > "$cutover_root/acceptance.txt"
chmod 600 "$cutover_root/acceptance.txt"
sed -n '1,40p' "$cutover_root/acceptance.txt"
```

Expected: source SHA is the candidate, every service is running/healthy, every
restart count is zero, and backend error markers equal zero.

- [ ] **Step 2: Perform a bounded stability observation**

Run on `home`:

```bash
sleep 60
test -z "$(docker inspect -f '{{.Name}}|{{.RestartCount}}' \
  restaurant_postgres restaurant_backend restaurant_frontend \
  restaurant_caddy restaurant_cloudflared | grep -Ev '\|0$')"
curl -fsS https://restaurant.labtutor.app/healthz >/dev/null
curl -fsS https://restaurant.labtutor.app/api/health >/dev/null
```

Expected: restart counts remain zero and both public routes still return HTTP
200.

- [ ] **Step 3: Retry the old host and invalidate only its restaurant tunnel**

First run locally:

```bash
printf '%s\n' \
  'test -d /home/khajiev13/apps/restaurant-mini-app && echo reachable' |
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant \
  "wsl.exe -d Ubuntu -- bash -s"
```

If it prints `reachable`, run:

```bash
printf '%s\n' \
  'set -eu' \
  'cd /home/khajiev13/apps/restaurant-mini-app' \
  'cutover_id=20260719-home-migration' \
  'install -m 600 .env .env.before-$cutover_id' \
  'if grep -q "^CLOUDFLARE_TUNNEL_TOKEN=" .env; then' \
  '  sed -i "s/^CLOUDFLARE_TUNNEL_TOKEN=.*/CLOUDFLARE_TUNNEL_TOKEN=disabled-on-restaurant/" .env' \
  'else' \
  '  printf "%s\n" "CLOUDFLARE_TUNNEL_TOKEN=disabled-on-restaurant" >> .env' \
  'fi' \
  'docker compose down' \
  'test -z "$(docker ps -q --filter name=restaurant_)"' |
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant \
  "wsl.exe -d Ubuntu -- bash -s"
```

Expected: the old restaurant stack is stopped and its active `.env` can no
longer authenticate a Cloudflare connector. The backup remains mode 600, and no
BitAgent command is issued.

If SSH still times out, record exactly `old_host_isolation=pending_unreachable`
in the acceptance file and report that residual risk; do not weaken the healthy
`home` deployment.

- [ ] **Step 4: Run the final acceptance gate**

Run on `home`:

```bash
cd /home/khajiev13/apps/restaurant-mini-app
test "$(git rev-parse HEAD)" = cbd82133d4a00dc545e611bb04bd07519509454d
test -z "$(git status --porcelain)"
test -z "$(docker inspect -f '{{.Name}}|{{.RestartCount}}' \
  restaurant_postgres restaurant_backend restaurant_frontend \
  restaurant_caddy restaurant_cloudflared | grep -Ev '\|0$')"
curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsS http://127.0.0.1:8080/api/health >/dev/null
curl -fsS https://restaurant.labtutor.app/healthz >/dev/null
curl -fsS https://restaurant.labtutor.app/api/health >/dev/null
docker ps -a --filter name=lab4_professor_ \
  --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}'
```

Expected: exact candidate, clean checkout, five zero-restart restaurant
containers, four healthy routes, and an unchanged BitAgent baseline.
