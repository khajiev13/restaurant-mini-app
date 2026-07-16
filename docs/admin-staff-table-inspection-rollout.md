# Admin and Staff Table Inspection Rollout

## Release boundary

This is a full-stack release of every commit in `origin/prod..CANDIDATE_SHA`.
It is not a table-inspection-only deployment. The candidate must contain both
the current `origin/main` and `origin/codex/alipos-inplace-total-fix`, and the
release owner must review the complete delta before production changes begin.
If either branch is not an ancestor of the pinned candidate, stop.

The production deployment is performed by the external `deploy-watcher`. It
polls `prod`, waits for the exact pushed SHA to pass the `CI` workflow, and then
runs one `docker compose up -d --build`. The database migrations must finish
before `prod` is pushed. Complete every production migration, configuration
check, watcher check, and rollback preparation step before that single
production push. Do not run `start.sh`, do not run a second manual build, and
do not manually recreate the application containers during normal rollout.

All commands marked **LOCAL** run from a clean release checkout. Commands
marked **LIVE / MANUAL** run only during an authorized production window. The
examples assume the existing SSH alias `restaurant`, Docker inside WSL, the
production containers `restaurant_postgres`, `restaurant_backend`, and
`restaurant_frontend`, and the systemd unit `deploy-watcher.service`. Discover
and verify the production checkout path and image names; do not guess them.

## Evidence and privacy boundary

The two feature-specific safe signals are exactly:

- Backend: `staff_table_status_reconcile claimed=<n> succeeded=<n> failed=<n> duration_ms=<n>`
- Frontend: `staff_tables_workspace_load_failed { status: <code|network> }`

The backend event contains counts and duration only. The frontend event
contains a status code or `network` only. This repository has no centralized
browser telemetry. Browser DevTools Console and Network are therefore the
authoritative source for controlled frontend failures and controlled HTTP 403
or 5xx results.

Never retain raw backend logs, request URLs, request or response headers,
request or response bodies, access tokens, AliPOS payloads, or customer,
table, local-order, provider-order, payment, or Telegram IDs. Do not enable
shell tracing. Do not run `docker inspect` or `docker compose config` in a mode
that prints container environments. Do not take screenshots of Headers or
Response panels. Git SHAs and immutable Docker image IDs are the only IDs kept
because they are required for an executable rollback.

The release record may contain only:

- pinned Git SHAs and the reviewed file/commit summary;
- Docker Compose image names, immutable image IDs, and unique rollback tags;
- migration/schema metadata, never table rows;
- UTC watch boundaries, eligible count, and one-way eligible-set fingerprint;
- request/status aggregates and the exact safe reconcile substrings above;
- manually recorded browser counts for failures and mutations.

## 1. Pin and review the candidate

### LOCAL

Fetch the release inputs and pin all moving references once:

```bash
set -euo pipefail
set +x

git fetch --prune origin
test -z "$(git status --porcelain)"

export PRE_PROD_SHA="$(git rev-parse origin/prod)"
export MAIN_SHA="$(git rev-parse origin/main)"
export INPLACE_FIX_SHA="$(git rev-parse origin/codex/alipos-inplace-total-fix)"
export CANDIDATE_SHA="$(git rev-parse HEAD)"

for sha in "$PRE_PROD_SHA" "$MAIN_SHA" "$INPLACE_FIX_SHA" "$CANDIDATE_SHA"; do
  test "$(git rev-parse "$sha^{commit}")" = "$sha"
done

test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
git merge-base --is-ancestor "$PRE_PROD_SHA" "$CANDIDATE_SHA"
git merge-base --is-ancestor "$MAIN_SHA" "$CANDIDATE_SHA"
git merge-base --is-ancestor "$INPLACE_FIX_SHA" "$CANDIDATE_SHA"
```

Confirm all three migrations exist in the exact candidate:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql
do
  git cat-file -e "$CANDIDATE_SHA:$migration"
done
```

Review the entire stack, not only the table-inspection commits:

```bash
git log --reverse --oneline "$PRE_PROD_SHA..$CANDIDATE_SHA"
git diff --stat "$PRE_PROD_SHA..$CANDIDATE_SHA"
git diff --name-status "$PRE_PROD_SHA..$CANDIDATE_SHA"
git diff --check "$PRE_PROD_SHA..$CANDIDATE_SHA"
git diff "$PRE_PROD_SHA..$CANDIDATE_SHA"
```

Record review approval against `PRE_PROD_SHA..CANDIDATE_SHA`. If the delta
contains any unreviewed sibling work, generated artifact, secret, or unrelated
change, stop. Any candidate amendment creates a new `CANDIDATE_SHA` and
requires this section and all local verification to be repeated.

## 2. Run the complete local gate once

### LOCAL

Reuse the existing healthy local PostgreSQL test container. Do not recreate it
between suites or migration passes:

```bash
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_postgres)" = healthy
```

Run the backend suite and Ruff with the release test database:

```bash
set -a
source .env
set +a

cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=55432 .venv/bin/python -m pytest -q --tb=no
.venv/bin/python -m ruff check .
cd ..
```

Run the complete frontend gate:

```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
cd ..
```

Apply all migrations twice, in chronological order, to that same container.
This is an idempotency check, not a request to start another Docker stack:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql
do
  for pass in 1 2; do
    docker exec -i restaurant_postgres sh -lc \
      'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "$migration"
  done
done
```

Run the documentation, Compose, whitespace, signal, and browse-only gates:

```bash
docker compose config --quiet

rg -n \
  "staff_table_status_reconcile|staff_tables_workspace_load_failed" \
  backend/app/services/staff_table_service.py \
  frontend/src/pages/staff/StaffTablesPage.tsx \
  frontend/src/pages/staff/StaffTableDetailPage.tsx \
  docs/admin-staff-table-inspection-rollout.md

pandoc -f gfm -t html \
  docs/admin-staff-table-inspection-rollout.md \
  -o /tmp/admin-staff-table-inspection-rollout.html

git diff --check "$PRE_PROD_SHA..$CANDIDATE_SHA"

! rg -n \
  "useCartStore|useTableOrderStore|checkout|createOrder" \
  frontend/src/pages/staff/StaffTablesPage.tsx \
  frontend/src/pages/staff/StaffTableDetailPage.tsx \
  frontend/src/components/staff/TableOrderSummary.tsx \
  frontend/src/components/menu/MenuCatalog.tsx

rg -n '^INPLACE_ONLINE_PAYMENT_ENABLED=false$' .env.example
rg -n 'inplace_online_payment_enabled: bool = False' backend/app/config.py

test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
```

All commands must exit zero. The online-payment configuration checks exist
only after the sibling branch is integrated and prove that code defaults to
disabled; they do not replace the production configuration check below.

## 3. Verify the production mechanism and rollback before release

### LIVE / MANUAL preflight; no application deployment

First inspect only non-secret unit metadata:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
WATCHER_UNIT=deploy-watcher.service
sudo -n systemctl show "$WATCHER_UNIT" \
  --property=FragmentPath \
  --property=ExecStart \
  --property=WorkingDirectory
sudo -n systemctl is-enabled --quiet "$WATCHER_UNIT"
sudo -n systemctl is-active --quiet "$WATCHER_UNIT"
'\'''
```

Privately inspect the referenced unit and executable on the host. Do not copy
their environment or raw output into release evidence. Confirm all of the
following from the actual deployed watcher source:

1. Its working directory is the production checkout and its remote is this
   repository.
2. It polls `origin/prod`, deploys the exact observed SHA only after that SHA's
   `CI` push workflow is green, and never treats another SHA's green run as
   approval.
3. One new approved SHA causes exactly one
   `docker compose up -d --build` from that working directory.
4. It exposes a privacy-safe deployment-cycle marker that can be counted
   without retaining raw logs.
5. It can be stopped and started with noninteractive `sudo -n systemctl`.

If any property is ambiguous, if `WorkingDirectory` is empty, or if a secret
would have to be printed to prove it, stop and repair/audit the deployment
mechanism separately.

In the private WSL release shell, export the exact safe marker verified in
step 4. It must contain no token, URL, business ID, or customer field:

```bash
export WATCHER_DEPLOY_MARKER='<exact audited safe marker>'
test -n "$WATCHER_DEPLOY_MARKER"
```

Prove pause and resume without touching containers:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
WATCHER_UNIT=deploy-watcher.service
sudo -n systemctl stop "$WATCHER_UNIT"
! sudo -n systemctl is-active --quiet "$WATCHER_UNIT"
sudo -n systemctl start "$WATCHER_UNIT"
sudo -n systemctl is-active --quiet "$WATCHER_UNIT"
'\'''
```

Check the `prod` branch protection/ruleset before relying on a direct push.
The repository workflow names the jobs `Backend Tests` and `Frontend Tests`:

```bash
REPO=khajiev13/restaurant-mini-app
if REQUIRED_CHECKS="$(gh api "repos/$REPO/branches/prod/protection" \
  --jq '.required_status_checks.contexts[]?' 2>/dev/null)"; then
  printf '%s\n' "$REQUIRED_CHECKS" | rg -qx 'Backend Tests'
  printf '%s\n' "$REQUIRED_CHECKS" | rg -qx 'Frontend Tests'
  printf 'prod_branch_protection=present\n'
else
  printf 'prod_branch_protection=absent\n'
fi

git push --dry-run origin "$CANDIDATE_SHA:refs/heads/prod"
```

If protection is present, honor it and require both jobs. An absent protection
endpoint is recorded but does not block this explicitly authorized direct
release when the watcher's exact-SHA green-CI gate has been audited. A ruleset
conflict, rejected dry run, or inability to prove exact-SHA watcher gating does
block the release. Do not claim that a pull request exists or bypass a rule.

### LIVE / MANUAL image discovery and rollback proof

Open a WSL shell on the host and substitute the already pinned 40-character
SHAs. Do not substitute branch names:

```bash
ssh restaurant wsl
```

Then run inside WSL:

```bash
set -euo pipefail
set +x
umask 077

export PRE_PROD_SHA='<40-character PRE_PROD_SHA>'
export CANDIDATE_SHA='<40-character CANDIDATE_SHA>'
WATCHER_UNIT=deploy-watcher.service

case "$PRE_PROD_SHA:$CANDIDATE_SHA" in
  *[!0-9a-f:]*|'') exit 1 ;;
esac

PROD_DIR="$(sudo -n systemctl show "$WATCHER_UNIT" \
  --property=WorkingDirectory --value)"
test -n "$PROD_DIR"
test -d "$PROD_DIR/.git"
cd "$PROD_DIR"

git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
test "$(git branch --show-current)" = prod
test -z "$(git status --porcelain)"

BACKEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_backend)"
FRONTEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_frontend)"
BACKEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_backend)"
FRONTEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_frontend)"

test -n "$BACKEND_COMPOSE_IMAGE"
test -n "$FRONTEND_COMPOSE_IMAGE"
COMPOSE_IMAGES="$(docker compose config --images)"
printf '%s\n' "$COMPOSE_IMAGES" | rg -Fx -- "$BACKEND_COMPOSE_IMAGE"
printf '%s\n' "$COMPOSE_IMAGES" | rg -Fx -- "$FRONTEND_COMPOSE_IMAGE"
unset COMPOSE_IMAGES
case "$BACKEND_IMAGE_ID:$FRONTEND_IMAGE_ID" in
  sha256:*:sha256:*) ;;
  *) exit 1 ;;
esac

ROLLBACK_KEY="staff-tables-${PRE_PROD_SHA%%????????????????????????????}-$(date -u +%Y%m%dT%H%M%SZ)"
BACKEND_ROLLBACK_TAG="restaurant-release-rollback/backend:$ROLLBACK_KEY"
FRONTEND_ROLLBACK_TAG="restaurant-release-rollback/frontend:$ROLLBACK_KEY"

docker image tag "$BACKEND_IMAGE_ID" "$BACKEND_ROLLBACK_TAG"
docker image tag "$FRONTEND_IMAGE_ID" "$FRONTEND_ROLLBACK_TAG"
test "$(docker image inspect --format '{{.Id}}' "$BACKEND_ROLLBACK_TAG")" = "$BACKEND_IMAGE_ID"
test "$(docker image inspect --format '{{.Id}}' "$FRONTEND_ROLLBACK_TAG")" = "$FRONTEND_IMAGE_ID"

ROLLBACK_DIR="$PROD_DIR/.release-rollback/$ROLLBACK_KEY"
mkdir -p "$ROLLBACK_DIR"
cat > "$ROLLBACK_DIR/images.env" <<EOF
PRE_PROD_SHA=$PRE_PROD_SHA
CANDIDATE_SHA=$CANDIDATE_SHA
BACKEND_COMPOSE_IMAGE=$BACKEND_COMPOSE_IMAGE
FRONTEND_COMPOSE_IMAGE=$FRONTEND_COMPOSE_IMAGE
BACKEND_IMAGE_ID=$BACKEND_IMAGE_ID
FRONTEND_IMAGE_ID=$FRONTEND_IMAGE_ID
BACKEND_ROLLBACK_TAG=$BACKEND_ROLLBACK_TAG
FRONTEND_ROLLBACK_TAG=$FRONTEND_ROLLBACK_TAG
EOF
chmod 600 "$ROLLBACK_DIR/images.env"

docker compose --dry-run up -d --no-build --force-recreate backend frontend >/dev/null
```

The rollback file contains no application secret. Record its path, Compose
image names, immutable IDs, and tags. If the unique tags do not resolve to the
saved immutable IDs, the watcher cannot be paused, or the exact no-build dry
run is unsupported, stop. Do not proceed on the theory that an old tag can be
reconstructed later.

## 4. Verify production configuration without printing values

### LIVE / MANUAL

Run in the same WSL production shell. This prints only a success marker:

```bash
set -euo pipefail
set +x
cd "$PROD_DIR"
set -a
source .env
set +a

test -n "${TABLE_ACCESS_SECRET:-}"
test -n "${JWT_SECRET:-}"
test "$TABLE_ACCESS_SECRET" != "$JWT_SECRET"
test "${#TABLE_ACCESS_SECRET}" -ge 64
[[ "$TABLE_ACCESS_SECRET" =~ ^[0-9A-Fa-f]+$ ]]

test "${INPLACE_ONLINE_PAYMENT_ENABLED:-}" = false
test -z "${INPLACE_ONLINE_PAYMENT_TEST_TELEGRAM_IDS:-}"

if [ -z "${BOOTSTRAP_ADMIN_TELEGRAM_IDS:-}" ]; then
  DURABLE_ADMIN_REQUIRED=1
else
  DURABLE_ADMIN_REQUIRED=0
fi

unset TABLE_ACCESS_SECRET JWT_SECRET INPLACE_ONLINE_PAYMENT_ENABLED
unset INPLACE_ONLINE_PAYMENT_TEST_TELEGRAM_IDS BOOTSTRAP_ADMIN_TELEGRAM_IDS
printf 'production_config_shape=ok\n'
```

`TABLE_ACCESS_SECRET` must be a separate strong secret, never the JWT fallback.
For this release the in-place online-payment global gate is explicitly false
and its tester allowlist is empty. If the gate is to be enabled later, that is
a separate controlled rollout.

There must also be a controlled admin path: either a durable admin already
exists or a narrowly controlled bootstrap admin input is present. The `role`
column does not exist until the first migration is applied, so run the
aggregate-only durable-admin check in Section 5, not here. Do not record
bootstrap IDs. If bootstrap is needed, the controlled admin must authenticate
after deployment, become durable, and broad bootstrap input must not be left
configured longer than necessary.

## 5. Pause the watcher and migrate before pushing `prod`

### LIVE / MANUAL

Schedule a low-traffic window. The 2026-07-07 migration deliberately drops and
recreates `uq_orders_one_active_delivery_per_staff`; index recreation takes a
database lock. Do not apply it during a delivery surge, and do not interrupt or
blindly retry it while DDL is in progress.

Pause the watcher and prove that `prod` has not moved:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
sudo -n systemctl stop deploy-watcher.service
! sudo -n systemctl is-active --quiet deploy-watcher.service
'\'''

git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test -z "$(git status --porcelain)"
```

Apply each production migration exactly once, in this order, using the
approved SSH/WSL/PostgreSQL-stdin pattern. These commands send the candidate's
reviewed SQL and print no environment values:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql
do
  ssh restaurant \
    'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
    < "$migration"
done
```

Do not run any of these production migrations a second time in this release.
Verify schema metadata only:

```bash
ssh restaurant \
  'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
  <<'SQL'
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE (table_name = 'users' AND column_name = 'role')
   OR (table_name = 'orders' AND column_name IN (
     'assigned_staff_id', 'assigned_at', 'delivered_at',
     'items_cost', 'delivery_info', 'table_id', 'table_title',
     'hall_id', 'hall_title', 'service_percent',
     'table_access_expires_at', 'alipos_sync_status', 'alipos_sync_error',
     'cancel_requested_at', 'client_request_id',
     'refund_sync_status', 'refund_sync_error',
     'alipos_status_check_attempted_at', 'alipos_status_checked_at'
   ))
ORDER BY table_name, column_name;

SELECT conname
FROM pg_constraint
WHERE conname = 'ck_users_role_valid';

SELECT indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_orders_assigned_staff_id',
    'idx_orders_delivered_at',
    'idx_orders_staff_available',
    'uq_orders_one_active_delivery_per_staff',
    'idx_orders_table_id',
    'idx_orders_alipos_sync_status',
    'idx_orders_refund_sync_status',
    'uq_orders_user_request',
    'idx_orders_inplace_workspace'
  )
ORDER BY indexname;
SQL
```

Compare the metadata output with all three migration files. If any column,
constraint, or index is absent, stop with the watcher paused. Do not push
`prod`. Diagnose the migration without dumping data or environments.

Now verify the controlled-admin path after the `role` column exists. Run in
the same WSL production checkout; this prints only an aggregate count:

```bash
set -a
source .env
set +a

if [ -z "${BOOTSTRAP_ADMIN_TELEGRAM_IDS:-}" ]; then
  DURABLE_ADMIN_REQUIRED=1
else
  DURABLE_ADMIN_REQUIRED=0
fi
unset BOOTSTRAP_ADMIN_TELEGRAM_IDS

DURABLE_ADMIN_COUNT="$(docker exec -i restaurant_postgres sh -lc \
  'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT count(*) FROM users WHERE role = 'admin';
SQL
)"

case "$DURABLE_ADMIN_COUNT" in
  ''|*[!0-9]*) exit 1 ;;
esac

if [ "$DURABLE_ADMIN_COUNT" -eq 0 ] && [ "$DURABLE_ADMIN_REQUIRED" -eq 1 ]; then
  printf 'no controlled admin path\n' >&2
  exit 1
fi

printf 'controlled_admin_path=ok durable_admin_count=%s\n' "$DURABLE_ADMIN_COUNT"
```

The old application containers remain running while the watcher is paused.

## 6. Push one pinned SHA, wait for exact CI, then deploy once

### LOCAL, then LIVE / MANUAL

Recheck the remote and push exactly the clean pinned commit as a non-force
fast-forward. Migration completion is a prerequisite for this command:

```bash
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test -z "$(git status --porcelain)"
git merge-base --is-ancestor "$PRE_PROD_SHA" "$CANDIDATE_SHA"

git push origin "$CANDIDATE_SHA:refs/heads/prod"
```

Find and watch only the `CI` push run whose `headSha` equals the pinned
candidate:

```bash
REPO=khajiev13/restaurant-mini-app
RUN_ID="$(gh run list \
  --repo "$REPO" \
  --workflow CI \
  --branch prod \
  --event push \
  --limit 20 \
  --json databaseId,headSha \
  --jq ".[] | select(.headSha == \"$CANDIDATE_SHA\") | .databaseId" \
  | head -n 1)"

test -n "$RUN_ID"
test "$(gh run view "$RUN_ID" --repo "$REPO" --json headSha --jq .headSha)" = "$CANDIDATE_SHA"
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
test "$(gh run view "$RUN_ID" --repo "$REPO" --json conclusion --jq .conclusion)" = success
```

If CI fails, keep the watcher paused and execute the non-force rollback-commit
portion of Section 10 before resuming it. Never deploy a different SHA because
its CI happened to be green.

Immediately before resuming the watcher, record a UTC deployment wait start:

```bash
export DEPLOY_WAIT_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Resume the watcher. Do not invoke Docker Compose or `start.sh` yourself:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
sudo -n systemctl start deploy-watcher.service
sudo -n systemctl is-active --quiet deploy-watcher.service
'\'''
```

Wait for the watcher to finish its one CI-gated build, then verify the exact
checkout and healthy containers in WSL:

```bash
cd "$PROD_DIR"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test "$(git rev-parse origin/prod)" = "$CANDIDATE_SHA"

test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy

curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsS http://127.0.0.1:8080/api/health >/dev/null

set -a
source .env
set +a
test -n "${PUBLIC_APP_URL:-}"
curl -fsS "${PUBLIC_APP_URL%/}/healthz" >/dev/null
curl -fsS "${PUBLIC_APP_URL%/}/api/health" >/dev/null
unset PUBLIC_APP_URL
```

Count the privacy-safe watcher cycle marker identified in preflight between
`DEPLOY_WAIT_START` and now. The aggregate must be exactly one; do not retain
raw journal output:

```bash
DEPLOY_WAIT_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
test -n "${WATCHER_DEPLOY_MARKER:-}"
DEPLOY_CYCLES="$(sudo -n journalctl \
  -u deploy-watcher.service \
  --since "$DEPLOY_WAIT_START" \
  --until "$DEPLOY_WAIT_END" \
  --no-pager \
  | rg -F -c -- "$WATCHER_DEPLOY_MARKER")"
test "$DEPLOY_CYCLES" -eq 1
printf 'watcher_deploy_cycles=%s\n' "$DEPLOY_CYCLES"
```

The variable must contain the exact marker verified in Section 3. An unset or
unsafe marker, two cycles, wrong checkout SHA, unhealthy container, or failed
local/public health check blocks acceptance and triggers rollback. Record the
new backend/frontend `Config.Image` names and immutable IDs without inspecting
environments.

## 7. Read-only smoke tests before the watch

### LIVE / MANUAL in controlled browser sessions

Use one controlled customer, one controlled staff user, and one controlled
admin. Open DevTools before requests. Disable cache only if that is normal for
the smoke; never enable request/response persistence outside the browser
session.

Before `WATCH_START`:

1. From the signed-in customer browser, issue a direct read of
   `/api/staff/tables` with the browser's existing JWT. The Network panel must
   show 403. Do not copy the token, request, headers, or body. Record only
   `customer_staff_tables_status=403`.
2. The controlled staff and admin Tables overview and one detail read must each
   show 200 in Network. A 401/403 is a release failure.
3. Transiently inspect the successful response shape and confirm it contains no
   customer identity/contact/address, access token, Multicard identifier,
   checkout URL, provider body, or OAuth field. Do not copy or screenshot the
   response.
4. Confirm staff navigation is `Tables | Delivery | Profile`; admin navigation
   is `Admin | Tables | Delivery | Profile`.
5. Confirm every current directory table appears, including a neutral table
   with no mini-app order. Do not induce an empty directory or AliPOS outage.
6. Where existing data permits, confirm synchronized items/totals combine
   correctly while original orders remain separate; processing/attention
   records do not increase synchronized totals.
7. Confirm Menu is browse-only and contains no add/remove, cart, checkout, or
   order-creation control. Do not submit a mutation.
8. Confirm Uzbek, Russian, and English layouts, and verify customer catalog and
   staff Delivery pages still load normally. Do not create, assign, deliver,
   cancel, refund, or pay for an order as part of this release smoke.

Browser Network is authoritative for the controlled 403/5xx result. Uvicorn
access-log counts are only an aggregate cross-check.

## 8. Controlled 15-minute watch

### LIVE / MANUAL

Use a stable provider window. Do not manufacture a production outage, clear
the directory cache, or induce an empty directory.

In WSL, define an eligible-set snapshot that emits a count and SHA-256
fingerprint only. Raw order IDs stream directly into `sha256sum`; they are
never printed, stored, or retained:

```bash
eligible_snapshot() {
  docker exec -i restaurant_postgres sh -lc \
    'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL' |
SELECT count(*)
FROM orders
WHERE discriminator = 'inplace'
  AND table_id IS NOT NULL
  AND alipos_order_id IS NOT NULL
  AND alipos_sync_status = 'synced'
  AND status NOT IN (
    'DELIVERED', 'CANCELLED', 'CANCELED',
    'AWAITING_PAYMENT', 'PAYMENT_FAILED', 'PAYMENT_REVIEW'
  )
  AND (payment_method = 'cash' OR payment_status = 'paid');

SELECT id::text
FROM orders
WHERE discriminator = 'inplace'
  AND table_id IS NOT NULL
  AND alipos_order_id IS NOT NULL
  AND alipos_sync_status = 'synced'
  AND status NOT IN (
    'DELIVERED', 'CANCELLED', 'CANCELED',
    'AWAITING_PAYMENT', 'PAYMENT_FAILED', 'PAYMENT_REVIEW'
  )
  AND (payment_method = 'cash' OR payment_status = 'paid')
ORDER BY id;
SQL
  {
    IFS= read -r eligible_count
    eligible_fingerprint="$(sha256sum | awk '{print $1}')"
    printf '%s|%s\n' "$eligible_count" "$eligible_fingerprint"
  }
}

IFS='|' read -r ELIGIBLE_START ELIGIBLE_FINGERPRINT_START \
  <<< "$(eligible_snapshot)"
case "$ELIGIBLE_START" in ''|*[!0-9]*) exit 1 ;; esac
```

Immediately after that snapshot, set the exact UTC boundary:

```bash
export WATCH_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

In both controlled staff and admin browsers, clear Console and Network so the
window starts clean. Keep `Preserve log` off to avoid retaining raw requests.
During the next 15 minutes:

- keep a Tables overview visible for at least two 15-second polling intervals;
- keep one table detail visible for at least two polling intervals;
- switch Tables to Menu and back;
- make four manual refreshes separated by at least five seconds;
- observe at least eight overview/detail GETs in controlled Network panels;
- verify no POST, PUT, PATCH, or DELETE request is caused by Tables, detail, or
  browse-only Menu;
- filter Console for `staff_tables_workspace_load_failed` and Network for
  failed requests, 403, and 5xx, but do not open/copy headers or bodies.

At 15 minutes, set the end boundary before any other action and snapshot the
eligible set again:

```bash
export WATCH_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
IFS='|' read -r ELIGIBLE_END ELIGIBLE_FINGERPRINT_END \
  <<< "$(eligible_snapshot)"
```

The count and fingerprint must both be unchanged:

```bash
test "$ELIGIBLE_END" = "$ELIGIBLE_START"
test "$ELIGIBLE_FINGERPRINT_END" = "$ELIGIBLE_FINGERPRINT_START"
```

If either differs, discard all rate evidence and restart a new full 15-minute
window. Do not save the underlying IDs and do not alter orders to stabilize the
set.

Aggregate backend logs remotely between the exact boundaries. This pipeline
never writes raw logs; it prints only status counts and exact safe reconcile
substrings:

```bash
docker logs \
  --since "$WATCH_START" \
  --until "$WATCH_END" \
  restaurant_backend 2>&1 \
| awk '
  /staff_table_status_reconcile / {
    if (match($0, /staff_table_status_reconcile claimed=[0-9]+ succeeded=[0-9]+ failed=[0-9]+ duration_ms=[0-9]+/)) {
      safe = substr($0, RSTART, RLENGTH)
      print safe
      reconcile_lines += 1
      split(safe, fields, " ")
      for (i = 1; i <= length(fields); i += 1) {
        split(fields[i], pair, "=")
        if (pair[1] == "claimed") claimed += pair[2]
        if (pair[1] == "succeeded") succeeded += pair[2]
        if (pair[1] == "failed") failed += pair[2]
      }
    } else {
      malformed_reconcile += 1
    }
  }

  {
    if (match($0, /"GET \/api\/staff\/tables[^ ]* HTTP\/[0-9.]+" [0-9][0-9][0-9]/)) {
      access = substr($0, RSTART, RLENGTH)
      split(access, parts, " ")
      status = parts[length(parts)] + 0
      workspace_reads += 1
      if (status >= 200 && status < 300) workspace_2xx += 1
      if (status == 403) workspace_403 += 1
      if (status >= 500) workspace_5xx += 1
    }
  }

  END {
    print "workspace_reads=" workspace_reads + 0
    print "workspace_2xx=" workspace_2xx + 0
    print "workspace_403=" workspace_403 + 0
    print "workspace_5xx=" workspace_5xx + 0
    print "reconcile_lines=" reconcile_lines + 0
    print "reconcile_malformed=" malformed_reconcile + 0
    print "claimed_total=" claimed + 0
    print "succeeded_total=" succeeded + 0
    print "failed_total=" failed + 0
    print "reconcile_balance_ok=" ((claimed + 0) == (succeeded + failed + 0) ? 1 : 0)
  }
'
```

Do not redirect `docker logs` before the sanitizer and do not retain shell
scrollback containing anything other than its sanitized output. Record from
the browsers only these aggregates:

```text
controlled_workspace_reads=<n>
controlled_403=<n>
controlled_5xx=<n>
failed_assets_or_api=<n>
frontend_failure_events=<n>
workspace_mutations=<n>
```

Do not retain Network exports or screenshots. Clear both DevTools panels after
the aggregate record is complete.

For an unchanged eligible set, the runaway-rate upper bound is:

```text
CLAIM_BOUND = ELIGIBLE_START * 31
```

Thirty-one allows a claim at both 30-second boundaries of a 15-minute window.
The automated cross-worker test remains the authoritative per-order throttle
proof; this production value is only a runaway-rate guard.

## 9. Acceptance criteria and rollback triggers

Accept the candidate only when every item below is true:

- `PRE_PROD_SHA`, `CANDIDATE_SHA`, the reviewed delta, exact green CI run, and
  one watcher deployment cycle are recorded.
- Checkout SHA equals `CANDIDATE_SHA`; backend, frontend, and Caddy are healthy;
  local and public health checks pass.
- The customer backend authorization smoke returned exactly 403 before
  `WATCH_START`; controlled staff and admin reads returned 200.
- Eligible start/end counts and one-way fingerprints are identical.
- Both the controlled browser count and sanitized access-log count contain at
  least eight workspace reads.
- Controlled browser Network contains zero authorized 403, zero 5xx, and zero
  failed candidate asset/API requests.
- Controlled Console contains zero
  `staff_tables_workspace_load_failed` events.
- Tables/detail/Menu caused zero POST, PUT, PATCH, or DELETE requests and browse
  mode exposed no mutation control.
- `claimed_total <= ELIGIBLE_START * 31`.
- `claimed_total = succeeded_total + failed_total`, every reconcile line
  matched the exact safe format, and `failed_total = 0` during the stable
  provider window.
- Privacy, staff/admin navigation, neutral/listed tables, synchronized totals,
  processing/attention exclusion, separate order boundaries, three languages,
  customer catalog, and Delivery read-only smokes all passed.

Do not accept a watch during a provider incident. Do not induce a provider
outage or empty directory to test failure behavior in production.

Immediate rollback triggers are:

- wrong checkout/image, unhealthy service, failed local/public health, more
  than one watcher deployment cycle, or watcher behavior outside its audit;
- any authorized staff/admin 401/403, any repeated 5xx with a healthy provider,
  or any failed candidate asset/API request;
- any forbidden response field, customer-bearing evidence, browse mutation
  control, or server mutation caused by the workspace;
- any frontend failure event during the stable watch;
- claim bound exceeded, malformed reconcile signal, reconciliation accounting
  mismatch, or any reconcile failure during a stable provider window;
- customer ordering, delivery, payment, refund, cancellation, or role behavior
  regression.

An eligible-set change invalidates and restarts the watch; it is not itself a
rollback trigger unless accompanied by a functional failure.

## 10. Immediate rollback

Rollback restores backend and frontend together. Leave all additive migration
columns, constraints, and indexes in place. Schema removal is a separately
reviewed maintenance change.

### LIVE / MANUAL: restore saved immutable images first

Pause the watcher before touching image tags:

```bash
sudo -n systemctl stop deploy-watcher.service
! sudo -n systemctl is-active --quiet deploy-watcher.service
```

Load the protected mapping created before deployment and verify every value:

```bash
set -euo pipefail
set +x
cd "$PROD_DIR"
source "$ROLLBACK_DIR/images.env"

test "$(docker image inspect --format '{{.Id}}' "$BACKEND_ROLLBACK_TAG")" = "$BACKEND_IMAGE_ID"
test "$(docker image inspect --format '{{.Id}}' "$FRONTEND_ROLLBACK_TAG")" = "$FRONTEND_IMAGE_ID"

docker image tag "$BACKEND_ROLLBACK_TAG" "$BACKEND_COMPOSE_IMAGE"
docker image tag "$FRONTEND_ROLLBACK_TAG" "$FRONTEND_COMPOSE_IMAGE"
test "$(docker image inspect --format '{{.Id}}' "$BACKEND_COMPOSE_IMAGE")" = "$BACKEND_IMAGE_ID"
test "$(docker image inspect --format '{{.Id}}' "$FRONTEND_COMPOSE_IMAGE")" = "$FRONTEND_IMAGE_ID"

docker compose up -d --no-build --force-recreate backend frontend
```

That is the only manual container recreation in the runbook. It must include
`--no-build`. Verify restored health immediately:

```bash
test "$(docker inspect --format '{{.Image}}' restaurant_backend)" = "$BACKEND_IMAGE_ID"
test "$(docker inspect --format '{{.Image}}' restaurant_frontend)" = "$FRONTEND_IMAGE_ID"
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend)" = healthy

curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsS http://127.0.0.1:8080/api/health >/dev/null

set -a
source .env
set +a
curl -fsS "${PUBLIC_APP_URL%/}/healthz" >/dev/null
curl -fsS "${PUBLIC_APP_URL%/}/api/health" >/dev/null
unset PUBLIC_APP_URL
```

### LOCAL: make `prod` a non-force rollback commit

Do not reset or force-push `prod`. Create a new commit whose tree is exactly
the old production tree and whose parent is the candidate:

```bash
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$CANDIDATE_SHA"

ROLLBACK_COMMIT="$(printf '%s\n' \
  "rollback: restore production $PRE_PROD_SHA" \
  | git commit-tree "$PRE_PROD_SHA^{tree}" -p "$CANDIDATE_SHA")"

test "$(git rev-parse "$ROLLBACK_COMMIT^{tree}")" = \
  "$(git rev-parse "$PRE_PROD_SHA^{tree}")"
test "$(git rev-parse "$ROLLBACK_COMMIT^1")" = "$CANDIDATE_SHA"

git push origin "$ROLLBACK_COMMIT:refs/heads/prod"
```

Find the `CI` push run whose `headSha` is exactly `ROLLBACK_COMMIT`, wait for
both jobs to pass using the Section 6 `gh run list/view/watch` procedure, and
keep the watcher paused throughout. After green CI, resume it:

```bash
sudo -n systemctl start deploy-watcher.service
sudo -n systemctl is-active --quiet deploy-watcher.service
```

The watcher will make the branch and running stack converge on the rollback
commit's old tree. Verify checkout tree equality, healthy containers, and
local/public health again. If the exact pause, tag, no-build restore, non-force
rollback commit, CI, or resume command cannot be verified live, block the
original release rather than improvising during an incident.

## Release record checklist

- [ ] Clean pinned `PRE_PROD_SHA`, `MAIN_SHA`, sibling SHA, and `CANDIDATE_SHA`
- [ ] Full `origin/prod..CANDIDATE_SHA` review approval
- [ ] Complete local backend, Ruff, frontend, build, Pandoc, static, and migration-twice gates
- [ ] Branch protection and exact-SHA CI gating verified
- [ ] Watcher working directory, pause/resume, one-build behavior, and marker verified
- [ ] Exact Compose image names, immutable IDs, rollback tags, and no-build dry run verified
- [ ] Secret shape, controlled admin path, and default-false online gate verified without values
- [ ] Three production migrations applied once in order before `prod` push; metadata verified
- [ ] Exact candidate CI green; watcher deployed exactly once; health and SHA verified
- [ ] Customer 403 and controlled staff/admin 200/privacy/read-only smokes passed
- [ ] Stable 15-minute watch met every numeric threshold
- [ ] No raw logs, URLs, headers, bodies, business IDs, tokens, or unsafe screenshots retained
