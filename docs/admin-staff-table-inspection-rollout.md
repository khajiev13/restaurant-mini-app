# Admin and Staff Table Inspection Rollout

## Release boundary

This is a full-stack release of every commit in `origin/prod..CANDIDATE_SHA`.
It is not a table-inspection-only deployment. The candidate must contain both
the current `origin/main` and `origin/codex/alipos-inplace-total-fix`, and the
release owner must review the complete delta before production changes begin.
If either branch is not an ancestor of the pinned candidate, stop.

The external `deploy-watcher` normally deploys `prod`, but this release's
exclusive legacy-pending cutover requires stricter ordering. Keep the watcher
stopped from the start of the freeze through the maintenance route, old-backend
drain and stop, database gates, migrations, exact-SHA CI, selective candidate
startup, and normal-route restoration. After exact-SHA CI succeeds, manually
fast-forward the clean production checkout to that SHA, build the candidate
backend and frontend exactly once, and start only the explicitly listed
candidate services with Caddy excluded. The archived maintenance Caddy must
remain active until the candidate backend and frontend are healthy. Restore
the archived normal Caddy source with `--no-build --no-deps`, verify routing,
and only then resume the watcher as an audited equal-SHA zero-marker no-op.

Complete every production migration, configuration check, watcher check, and
rollback preparation step before the single production push. Do not run
`start.sh`, do not let the watcher build during the cutover, and do not run a
second application build. If the watcher cannot be held or its equal-SHA no-op
cannot be proved, stop the release. An incident adds one four-service no-build
restore; rollback checkout convergence is manual and the resumed watcher must
again be an audited zero-marker no-op, never a rebuild.

Use two explicit, persistent terminals for the whole release:

- **Terminal A — LOCAL** is a clean release checkout on the operator's
  workstation. Local Git, GitHub CLI, CI, push, and SSH commands run here.
- **Terminal B — WSL** is opened once with `ssh restaurant wsl`. Production
  checkout, Docker, schema, image, and watch commands run here. Keep it open,
  but make every block self-contained by sourcing the protected remote state
  pointer described in Section 3.

Commands marked **LIVE / MANUAL** run only during an authorized production
window. The examples assume the existing SSH alias `restaurant`, Docker inside
WSL, the production containers `restaurant_postgres`, `restaurant_backend`,
`restaurant_frontend`, `restaurant_caddy`, and `restaurant_cloudflared`, and
the systemd unit `deploy-watcher.service`. Discover and verify the production
checkout, Compose project name, and image names; do not guess them. Every
watcher stop/start command is shown as an explicit LOCAL-to-WSL SSH command so
there is no ambiguity about which systemd instance it controls.

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
- the four staff-take timeout values and a non-secret proxy-evidence reference;
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

LOCAL_STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/restaurant-mini-app/releases"
mkdir -p "$LOCAL_STATE_ROOT"
chmod 700 "$LOCAL_STATE_ROOT"
LOCAL_RELEASE_STATE="$LOCAL_STATE_ROOT/staff-tables-$CANDIDATE_SHA.env"
{
  printf 'PRE_PROD_SHA=%q\n' "$PRE_PROD_SHA"
  printf 'MAIN_SHA=%q\n' "$MAIN_SHA"
  printf 'INPLACE_FIX_SHA=%q\n' "$INPLACE_FIX_SHA"
  printf 'CANDIDATE_SHA=%q\n' "$CANDIDATE_SHA"
  printf 'RELEASE_CHECKOUT=%q\n' "$PWD"
} > "$LOCAL_RELEASE_STATE"
chmod 600 "$LOCAL_RELEASE_STATE"
```

At the start of every later **Terminal A — LOCAL** block, set
`LOCAL_RELEASE_STATE` to this recorded path, source it, and assert the checkout
and SHAs before use:

```bash
set -euo pipefail
set +x
umask 077
LOCAL_RELEASE_STATE='<absolute path recorded above>'
test -r "$LOCAL_RELEASE_STATE"
source "$LOCAL_RELEASE_STATE"
cd "$RELEASE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test "$(git rev-parse "$PRE_PROD_SHA^{commit}")" = "$PRE_PROD_SHA"
```

Confirm all four migrations exist in the exact candidate:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql \
  database/migrations/2026-07-18-release-safety.sql
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

Use the installed Python 3.12 environment rather than the worktree's unusable
Python 3.9 environment. Run the full backend suite and Ruff with the release
test database. The full suite may skip the opt-in destructive proof; the
separate proof immediately below must pass with zero skips:

```bash
set -a
source .env
set +a
BACKEND_PYTHON=/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python
test -x "$BACKEND_PYTHON"

cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
  "$BACKEND_PYTHON" -m pytest -q --tb=no
"$BACKEND_PYTHON" -m ruff check .
cd ..
```

Prove the final-admin concurrency behavior once for this exact candidate in a
fresh, volume-free PostgreSQL container. This command uses a random
loopback-only port and an exact `admin_concurrency_gate_` database name. It
does not build an application image and must never target `restaurant_db`, the
existing local PostgreSQL volume, or production. Do not repeat it for an
unchanged candidate. Run the block from the release checkout root; it enters
and leaves `backend/` explicitly:

```bash
set -euo pipefail
cd backend
GATE_NONCE="$(date -u +%Y%m%d%H%M%S)-$$"
GATE_CONTAINER="admin-concurrency-gate-$GATE_NONCE"
GATE_DB="admin_concurrency_gate_${GATE_NONCE//-/_}"
GATE_USER=gate_user
GATE_PASSWORD=gate_password_only
BACKEND_PYTHON=/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python
test -x "$BACKEND_PYTHON"
cleanup_admin_gate() { docker rm -f "$GATE_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup_admin_gate EXIT INT TERM

docker run -d --rm \
  --name "$GATE_CONTAINER" \
  -e POSTGRES_USER="$GATE_USER" \
  -e POSTGRES_PASSWORD="$GATE_PASSWORD" \
  -e POSTGRES_DB="$GATE_DB" \
  -p 127.0.0.1::5432 \
  postgres:16-alpine >/dev/null

for _ in $(seq 1 60); do
  docker exec "$GATE_CONTAINER" pg_isready -U "$GATE_USER" -d "$GATE_DB" >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$GATE_CONTAINER" pg_isready -U "$GATE_USER" -d "$GATE_DB" >/dev/null
GATE_PORT="$(docker port "$GATE_CONTAINER" 5432/tcp | awk -F: '{print $NF}')"
case "$GATE_PORT" in ''|*[!0-9]*) exit 1 ;; esac

POSTGRES_HOST=127.0.0.1 \
POSTGRES_PORT="$GATE_PORT" \
POSTGRES_USER="$GATE_USER" \
POSTGRES_PASSWORD="$GATE_PASSWORD" \
POSTGRES_DB="$GATE_DB" \
TELEGRAM_BOT_TOKEN=test_token \
JWT_SECRET=test_secret \
ALIPOS_API_CLIENT_ID=test_client_id \
ALIPOS_API_CLIENT_SECRET=test_client_secret \
ALIPOS_RESTAURANT_ID=test-restaurant-id \
RUN_DESTRUCTIVE_POSTGRES_TESTS=1 \
  "$BACKEND_PYTHON" -m pytest \
    tests/test_admin_user_service.py::test_concurrent_admin_demotions_do_not_remove_all_admins \
    -q --junitxml=/tmp/admin-concurrency-gate.xml

"$BACKEND_PYTHON" -c '
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
totals = tuple(sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped"))
assert totals == (1, 0, 0, 0), totals
' /tmp/admin-concurrency-gate.xml

docker stop --time 30 "$GATE_CONTAINER" >/dev/null
trap - EXIT INT TERM
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
  database/migrations/2026-07-15-staff-table-inspection.sql \
  database/migrations/2026-07-18-release-safety.sql
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

rg -n '^    staff_take_order_provider_timeout_seconds: float = 8\.0$' \
  backend/app/config.py
rg -n '^    staff_take_order_operation_timeout_seconds: float = 10\.0$' \
  backend/app/config.py
rg -n '^const TAKE_ORDER_TIMEOUT_MS = 15000;$' \
  frontend/src/services/staffApi.ts

test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
```

All commands must exit zero. The online-payment configuration checks exist
only after the sibling branch is integrated and prove that code defaults to
disabled; they do not replace the production configuration check below.

## 3. Verify the production mechanism and rollback before release

### LIVE / MANUAL watcher audit; no application deployment

From **Terminal A — LOCAL**, print only non-secret unit metadata. Deliberately
do not request `ExecStart`; command arguments can contain tokens:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
WATCHER_UNIT=deploy-watcher.service
sudo -n systemctl show "$WATCHER_UNIT" \
  --property=FragmentPath \
  --property=WorkingDirectory
sudo -n systemctl is-enabled --quiet "$WATCHER_UNIT"
sudo -n systemctl is-active --quiet "$WATCHER_UNIT"
'\'''
```

Privately inspect the referenced unit, environment, and executable on the host.
Do not emit raw command, environment, or file output to the terminal and do not
retain it as evidence. Record only a yes/no audit result. Confirm all of these:

1. Its working directory is the production checkout and its remote is this
   repository.
2. It polls `origin/prod`, deploys the exact observed SHA only after that SHA's
   `CI` push workflow is green, and never accepts another SHA's run.
3. One new approved SHA causes exactly one normal
   `docker compose up -d --build` from that working directory.
4. It has an exact privacy-safe deployment-cycle marker that can be counted
   without retaining raw logs.
5. It can be stopped and started with noninteractive `sudo -n systemctl`.
6. When its clean checkout `HEAD` already equals `origin/prod`, starting or
   polling it is a strict no-op: it runs no Compose build/up command, emits no
   deployment-cycle marker, and does not recreate or replace a container.

If any property is ambiguous, if `WorkingDirectory` is empty, or if the audit
cannot be completed without displaying a secret, or equal-SHA no-op behavior
cannot be proven from the deployed source, stop and repair/review the watcher
separately. Rollback in this runbook depends on that no-op guarantee.

### LIVE / MANUAL staff take-order timeout ordering; no application request

The release requires this strict ordering on the deployed public request path:

```text
AliPOS provider read 8s < backend take operation 10s < browser mutation 15s < deployed proxy timeout
```

First verify the effective backend values without printing the production
environment. From **Terminal A — LOCAL**, this command emits only the two
approved numeric deadlines:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
WATCHER_UNIT=deploy-watcher.service
PROD_DIR="$(sudo -n systemctl show "$WATCHER_UNIT" \
  --property=WorkingDirectory --value)"
test -n "$PROD_DIR"
cd "$PROD_DIR"
set -a
source .env
set +a
export STAFF_TAKE_PROVIDER_EFFECTIVE="${STAFF_TAKE_ORDER_PROVIDER_TIMEOUT_SECONDS:-8.0}"
export STAFF_TAKE_OPERATION_EFFECTIVE="${STAFF_TAKE_ORDER_OPERATION_TIMEOUT_SECONDS:-10.0}"
python3 - <<'PY'
from decimal import Decimal
import os

provider = Decimal(os.environ["STAFF_TAKE_PROVIDER_EFFECTIVE"])
operation = Decimal(os.environ["STAFF_TAKE_OPERATION_EFFECTIVE"])
if provider != Decimal("8.0") or operation != Decimal("10.0"):
    raise SystemExit("staff take backend timeout gate failed")
print("staff_take_backend_timeouts=8s<10s")
PY
unset STAFF_TAKE_PROVIDER_EFFECTIVE STAFF_TAKE_OPERATION_EFFECTIVE
'\'''
```

Next privately inspect every deployed proxy layer on the public path, including
the Cloudflare edge/tunnel policy and Caddy's active configuration. Obtain a
reviewed, non-secret evidence reference and the lowest proven request-timeout
lower bound across those layers. If a layer is documented as unbounded, the
evidence must explicitly establish that; record a conservative proven lower
bound for the numeric gate. Run locally:

```bash
DEPLOYED_PROXY_TIMEOUT_LOWER_BOUND_SECONDS='<whole seconds from reviewed deployed-path proof>'
DEPLOYED_PROXY_TIMEOUT_EVIDENCE='<non-secret release-record reference>'
case "$DEPLOYED_PROXY_TIMEOUT_LOWER_BOUND_SECONDS" in
  ''|'<whole seconds from reviewed deployed-path proof>'|*[!0-9]*) exit 1 ;;
esac
case "$DEPLOYED_PROXY_TIMEOUT_EVIDENCE" in
  ''|'<non-secret release-record reference>') exit 1 ;;
esac
test "$DEPLOYED_PROXY_TIMEOUT_LOWER_BOUND_SECONDS" -gt 15
printf 'staff_take_timeout_ordering=8s<10s<15s<proxy\n'
```

The repository's current plain Caddy `reverse_proxy` block, a healthy proxy,
and a 15-second health-check `curl` do **not** prove a public request timeout
greater than 15 seconds. If the effective backend values are not exactly 8 and
10 seconds, any proxy layer is unreviewed, the lowest proven proxy bound is not
strictly greater than 15 seconds, or the evidence reference is missing, stop
the release before production mutation.

Prove pause and resume from **Terminal A — LOCAL** without touching containers:

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

### LOCAL branch rules and pre-created rollback commit

In **Terminal A — LOCAL**, source and verify `LOCAL_RELEASE_STATE` as described
in Section 1. The candidate workflow jobs are named `Backend Tests`,
`Admin concurrency gate`, and `Frontend Tests`. This direct-release procedure
is valid only when both classic branch protection and all applicable repository
rules are absent.

```bash
REPO=khajiev13/restaurant-mini-app
DIRECT_RELEASE_AUTHORIZATION='<release-record reference for explicit authorization>'
WATCHER_EXACT_SHA_AUDITED=1
case "$DIRECT_RELEASE_AUTHORIZATION" in
  ''|'<release-record reference for explicit authorization>') exit 1 ;;
esac
test "$WATCHER_EXACT_SHA_AUDITED" -eq 1

gh auth status --hostname github.com >/dev/null 2>&1
test "$(gh api "repos/$REPO" --jq .full_name)" = "$REPO"
test "$(gh api "repos/$REPO/branches/prod" --jq .name)" = prod
test "$(gh api "repos/$REPO" --jq '.permissions.admin')" = true

AUTHORITY_RESPONSE="$(mktemp)"
AUTHORITY_ERROR="$(mktemp)"
if gh api --include user >"$AUTHORITY_RESPONSE" 2>"$AUTHORITY_ERROR"; then
  AUTHORITY_RC=0
else
  AUTHORITY_RC=$?
fi
AUTHORITY_HTTP="$(awk '
  toupper($1) ~ /^HTTP\// { code=$2 }
  END { print code }
' "$AUTHORITY_RESPONSE")"
AUTHORITY_SCOPES="$(awk '
  {
    line=$0
    if (tolower(line) ~ /^x-oauth-scopes:/) {
      sub(/^[^:]*:[[:space:]]*/, "", line)
      gsub(/\r/, "", line)
      gsub(/[[:space:]]/, "", line)
      scopes=line
    }
  }
  END { print scopes }
' "$AUTHORITY_RESPONSE")"
rm -f "$AUTHORITY_RESPONSE" "$AUTHORITY_ERROR"
test "$AUTHORITY_HTTP:$AUTHORITY_RC" = 200:0
case ",$AUTHORITY_SCOPES," in
  *,repo,*) ;;
  *) printf 'classic repo scope cannot be proven; direct release blocked\n' >&2; exit 1 ;;
esac
unset AUTHORITY_SCOPES

PROTECTION_RESPONSE="$(mktemp)"
PROTECTION_ERROR="$(mktemp)"
if gh api --include "repos/$REPO/branches/prod/protection" \
  >"$PROTECTION_RESPONSE" 2>"$PROTECTION_ERROR"; then
  PROTECTION_RC=0
else
  PROTECTION_RC=$?
fi
PROTECTION_HTTP="$(awk '
  toupper($1) ~ /^HTTP\// { code=$2 }
  END { print code }
' "$PROTECTION_RESPONSE")"
rm -f "$PROTECTION_RESPONSE" "$PROTECTION_ERROR"

case "$PROTECTION_HTTP:$PROTECTION_RC" in
  404:*) printf 'classic_branch_protection=absent\n' ;;
  200:0)
    printf 'classic branch protection is present; direct release blocked\n' >&2
    exit 1
    ;;
  *)
    printf 'branch protection check was not an authenticated 404\n' >&2
    exit 1
    ;;
esac

APPLICABLE_RULE_COUNT="$(gh api \
  "repos/$REPO/rules/branches/prod" --jq 'length')"
case "$APPLICABLE_RULE_COUNT" in ''|*[!0-9]*) exit 1 ;; esac
if [ "$APPLICABLE_RULE_COUNT" -ne 0 ]; then
  printf 'applicable rules exist; direct release blocked\n' >&2
  exit 1
fi
printf 'applicable_branch_rules=absent\n'

ROLLBACK_COMMIT="$(printf '%s\n' \
  "rollback: restore production $PRE_PROD_SHA" \
  | git commit-tree "$PRE_PROD_SHA^{tree}" -p "$CANDIDATE_SHA")"
test "$(git rev-parse "$ROLLBACK_COMMIT^{tree}")" = \
  "$(git rev-parse "$PRE_PROD_SHA^{tree}")"
test "$(git rev-parse "$ROLLBACK_COMMIT^1")" = "$CANDIDATE_SHA"
printf 'ROLLBACK_COMMIT=%q\n' "$ROLLBACK_COMMIT" >> "$LOCAL_RELEASE_STATE"
chmod 600 "$LOCAL_RELEASE_STATE"

git push --dry-run origin "$CANDIDATE_SHA:refs/heads/prod"
git push --dry-run origin "$ROLLBACK_COMMIT:refs/heads/prod"
```

The protection 404 is treated as conclusive only because two independent
authority checks ran first without printing credential data: the active
credential proved the classic `repo` OAuth scope and the authenticated viewer
proved ADMIN permission on this repository. A missing scope header, a
fine-grained credential whose Administration-read permission cannot be proved
by this procedure, non-ADMIN permission, authentication/network failure, or an
unreadable rules endpoint blocks this path. A 200 protection response or any
applicable rule also blocks it. Use a separate, reviewed protected-branch
promotion and rollback procedure; do not bypass the rule or improvise a PR.
Absence is allowed only with this authority proof, explicit user
authorization, and the privately audited exact-SHA watcher gate.

The rollback commit is created before production mutation. Its parent is the
candidate and its tree is exactly pre-production, so both the candidate and
incident rollback are non-force fast-forwards. Record `ROLLBACK_COMMIT`; never
recreate it during an incident.

### LIVE / MANUAL four-service rollback proof

Now open **Terminal B — WSL**. Do not set or export the marker before this
shell is open:

```bash
ssh restaurant wsl
```

Inside **Terminal B — WSL**, substitute only the deliberate preflight inputs
below. `WATCHER_DEPLOY_MARKER` must be the exact marker from the private audit;
it may contain no token, URL, business ID, or customer field.

```bash
set -euo pipefail
set +x
umask 077

PRE_PROD_SHA='<40-character PRE_PROD_SHA>'
CANDIDATE_SHA='<40-character CANDIDATE_SHA>'
ROLLBACK_COMMIT='<40-character pre-created ROLLBACK_COMMIT>'
WATCHER_DEPLOY_MARKER='<exact audited privacy-safe marker>'
WATCHER_AUDIT_OK=1
WATCHER_EXACT_SHA_AUDITED=1
WATCHER_EQUAL_SHA_NOOP_AUDITED=1
WATCHER_UNIT=deploy-watcher.service

for sha in "$PRE_PROD_SHA" "$CANDIDATE_SHA" "$ROLLBACK_COMMIT"; do
  case "$sha" in ????????-*) exit 1 ;; esac
  test "${#sha}" -eq 40
  case "$sha" in *[!0-9a-f]*) exit 1 ;; esac
done
test "$WATCHER_AUDIT_OK" -eq 1
test "$WATCHER_EXACT_SHA_AUDITED" -eq 1
test "$WATCHER_EQUAL_SHA_NOOP_AUDITED" -eq 1
[[ "$WATCHER_DEPLOY_MARKER" =~ ^[A-Za-z0-9_.:=-]+([[:space:]][A-Za-z0-9_.:=-]+)*$ ]]

PROD_DIR="$(sudo -n systemctl show "$WATCHER_UNIT" \
  --property=WorkingDirectory --value)"
test -n "$PROD_DIR"
test -d "$PROD_DIR/.git"
cd "$PROD_DIR"
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
test "$(git branch --show-current)" = prod
test -z "$(git status --porcelain)"

STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/restaurant-mini-app/rollbacks"
mkdir -p "$STATE_ROOT"
chmod 700 "$STATE_ROOT"
ROLLBACK_KEY="staff-tables-${PRE_PROD_SHA:0:12}-$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK_DIR="$STATE_ROOT/$ROLLBACK_KEY"
PRE_PROD_SOURCE="$ROLLBACK_DIR/pre-prod-source"
mkdir -p "$PRE_PROD_SOURCE"
chmod 700 "$ROLLBACK_DIR" "$PRE_PROD_SOURCE"
case "$ROLLBACK_DIR/" in "$PROD_DIR"/*) exit 1 ;; esac

git archive "$PRE_PROD_SHA" | tar -xf - -C "$PRE_PROD_SOURCE"
chmod -R go-rwx "$PRE_PROD_SOURCE"
test -f "$PRE_PROD_SOURCE/docker-compose.yml"
test -f "$PRE_PROD_SOURCE/Caddyfile"
cmp "$PRE_PROD_SOURCE/docker-compose.yml" \
  <(git show "$PRE_PROD_SHA:docker-compose.yml")
cmp "$PRE_PROD_SOURCE/Caddyfile" <(git show "$PRE_PROD_SHA:Caddyfile")
PRE_PROD_COMPOSE_SHA256="$(sha256sum "$PRE_PROD_SOURCE/docker-compose.yml" | awk '{print $1}')"
PRE_PROD_CADDY_SHA256="$(sha256sum "$PRE_PROD_SOURCE/Caddyfile" | awk '{print $1}')"
for digest in "$PRE_PROD_COMPOSE_SHA256" "$PRE_PROD_CADDY_SHA256"; do
  test "${#digest}" -eq 64
  case "$digest" in *[!0-9a-f]*) exit 1 ;; esac
done
test ! -e "$PRE_PROD_SOURCE/.env"
ln -s "$PROD_DIR/.env" "$PRE_PROD_SOURCE/.env"
test "$(readlink -f "$PRE_PROD_SOURCE/.env")" = \
  "$(readlink -f "$PROD_DIR/.env")"

COMPOSE_PROJECT_NAME="$(docker inspect --format \
  '{{index .Config.Labels "com.docker.compose.project"}}' restaurant_backend)"
test -n "$COMPOSE_PROJECT_NAME"
for mapping in \
  backend:restaurant_backend \
  frontend:restaurant_frontend \
  caddy:restaurant_caddy \
  cloudflared:restaurant_cloudflared
do
  SERVICE_NAME="${mapping%%:*}"
  CONTAINER_NAME="${mapping#*:}"
  test "$(docker inspect --format \
    '{{index .Config.Labels "com.docker.compose.project"}}' "$CONTAINER_NAME")" = \
    "$COMPOSE_PROJECT_NAME"
  test "$(docker inspect --format \
    '{{index .Config.Labels "com.docker.compose.service"}}' "$CONTAINER_NAME")" = \
    "$SERVICE_NAME"
done

BACKEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_backend)"
FRONTEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_frontend)"
CADDY_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_caddy)"
CLOUDFLARED_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_cloudflared)"
BACKEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_backend)"
FRONTEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_frontend)"
CADDY_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_caddy)"
CLOUDFLARED_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_cloudflared)"
BACKEND_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_backend)"
FRONTEND_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_frontend)"
CADDY_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_caddy)"
CLOUDFLARED_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_cloudflared)"
POSTGRES_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_postgres)"

for id in "$BACKEND_IMAGE_ID" "$FRONTEND_IMAGE_ID" "$CADDY_IMAGE_ID" \
  "$CLOUDFLARED_IMAGE_ID"; do
  case "$id" in sha256:*) ;; *) exit 1 ;; esac
done

COMPOSE_IMAGES="$(docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PROD_DIR" \
  --env-file "$PROD_DIR/.env" \
  -f "$PROD_DIR/docker-compose.yml" config --images)"
for image in "$BACKEND_COMPOSE_IMAGE" "$FRONTEND_COMPOSE_IMAGE" \
  "$CADDY_COMPOSE_IMAGE" "$CLOUDFLARED_COMPOSE_IMAGE"; do
  printf '%s\n' "$COMPOSE_IMAGES" | rg -Fx -- "$image" >/dev/null
done
unset COMPOSE_IMAGES

test "$(docker inspect --format '{{len .Config.Cmd}}' restaurant_cloudflared)" -eq 7
test "$(docker inspect --format '{{index .Config.Cmd 2}}' restaurant_cloudflared)" = --protocol
test "$(docker inspect --format '{{index .Config.Cmd 3}}' restaurant_cloudflared)" = quic
test "$(docker inspect --format '{{index .Config.Cmd 5}}' restaurant_cloudflared)" = --token

BACKEND_ROLLBACK_TAG="restaurant-release-rollback/backend:$ROLLBACK_KEY"
FRONTEND_ROLLBACK_TAG="restaurant-release-rollback/frontend:$ROLLBACK_KEY"
CADDY_ROLLBACK_TAG="restaurant-release-rollback/caddy:$ROLLBACK_KEY"
CLOUDFLARED_ROLLBACK_TAG="restaurant-release-rollback/cloudflared:$ROLLBACK_KEY"
docker image tag "$BACKEND_IMAGE_ID" "$BACKEND_ROLLBACK_TAG"
docker image tag "$FRONTEND_IMAGE_ID" "$FRONTEND_ROLLBACK_TAG"
docker image tag "$CADDY_IMAGE_ID" "$CADDY_ROLLBACK_TAG"
docker image tag "$CLOUDFLARED_IMAGE_ID" "$CLOUDFLARED_ROLLBACK_TAG"

for pair in \
  "$BACKEND_ROLLBACK_TAG|$BACKEND_IMAGE_ID" \
  "$FRONTEND_ROLLBACK_TAG|$FRONTEND_IMAGE_ID" \
  "$CADDY_ROLLBACK_TAG|$CADDY_IMAGE_ID" \
  "$CLOUDFLARED_ROLLBACK_TAG|$CLOUDFLARED_IMAGE_ID"
do
  TAG="${pair%%|*}"
  IMAGE_ID="${pair#*|}"
  test "$(docker image inspect --format '{{.Id}}' "$TAG")" = "$IMAGE_ID"
done

ROLLBACK_OVERRIDE="$ROLLBACK_DIR/rollback-images.yml"
cat > "$ROLLBACK_OVERRIDE" <<EOF
services:
  backend:
    image: $BACKEND_ROLLBACK_TAG
  frontend:
    image: $FRONTEND_ROLLBACK_TAG
  caddy:
    image: $CADDY_ROLLBACK_TAG
  cloudflared:
    image: $CLOUDFLARED_ROLLBACK_TAG
EOF
chmod 600 "$ROLLBACK_OVERRIDE"

REMOTE_RELEASE_STATE="$ROLLBACK_DIR/release.env"
for variable in \
  PRE_PROD_SHA CANDIDATE_SHA ROLLBACK_COMMIT PROD_DIR COMPOSE_PROJECT_NAME \
  ROLLBACK_DIR PRE_PROD_SOURCE PRE_PROD_COMPOSE_SHA256 \
  PRE_PROD_CADDY_SHA256 ROLLBACK_OVERRIDE WATCHER_DEPLOY_MARKER \
  WATCHER_EQUAL_SHA_NOOP_AUDITED \
  BACKEND_COMPOSE_IMAGE FRONTEND_COMPOSE_IMAGE CADDY_COMPOSE_IMAGE \
  CLOUDFLARED_COMPOSE_IMAGE BACKEND_IMAGE_ID FRONTEND_IMAGE_ID \
  CADDY_IMAGE_ID CLOUDFLARED_IMAGE_ID BACKEND_CONTAINER_ID \
  FRONTEND_CONTAINER_ID CADDY_CONTAINER_ID CLOUDFLARED_CONTAINER_ID \
  POSTGRES_CONTAINER_ID BACKEND_ROLLBACK_TAG FRONTEND_ROLLBACK_TAG \
  CADDY_ROLLBACK_TAG CLOUDFLARED_ROLLBACK_TAG
do
  printf '%s=%q\n' "$variable" "${!variable}"
done > "$REMOTE_RELEASE_STATE"
chmod 600 "$REMOTE_RELEASE_STATE"

REMOTE_POINTER="$STATE_ROOT/current-staff-tables.env"
printf 'ROLLBACK_DIR=%q\n' "$ROLLBACK_DIR" > "$REMOTE_POINTER"
chmod 600 "$REMOTE_POINTER"

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PRE_PROD_SOURCE" \
  --env-file "$PROD_DIR/.env" \
  -f "$PRE_PROD_SOURCE/docker-compose.yml" \
  -f "$ROLLBACK_OVERRIDE" \
  --dry-run up -d --no-build --force-recreate --no-deps \
  backend frontend caddy cloudflared >/dev/null
```

The rollback directory is mode 700, every state file is mode 600, and the
archived source, Compose project name, old service image/container IDs, unique
tags, Caddyfile, and pre-release `quic` command are recorded outside
`PROD_DIR`. The dry run uses that exact PRE_PROD source, the current production
`.env`, the exact Compose project, and all four non-database services. If any
mapping, permission, tag, command shape, or dry run fails, stop. PostgreSQL is
never included and `--no-deps` prevents Compose from recreating it.

At the start of every later **Terminal B — WSL** block, re-establish and test
the complete remote context with this preamble:

```bash
set -euo pipefail
set +x
umask 077
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/restaurant-mini-app/rollbacks"
REMOTE_POINTER="$STATE_ROOT/current-staff-tables.env"
test -r "$REMOTE_POINTER"
source "$REMOTE_POINTER"
test -d "$ROLLBACK_DIR"
test -r "$ROLLBACK_DIR/release.env"
source "$ROLLBACK_DIR/release.env"
test -d "$PROD_DIR/.git"
test -d "$PRE_PROD_SOURCE"
test -n "$WATCHER_DEPLOY_MARKER"
test "$WATCHER_EQUAL_SHA_NOOP_AUDITED" -eq 1
test "${#ROLLBACK_COMMIT}" -eq 40
case "$ROLLBACK_COMMIT" in *[!0-9a-f]*) exit 1 ;; esac
```

## 4. Verify production configuration without printing values

### LIVE / MANUAL

#### Telegram webhook secret freeze

The current production `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET`
values are frozen for this release. Do not generate, replace, rotate, or
otherwise change either value before, during, or after this rollout's
acceptance or rollback path. Rotation is prohibited because the application
accepts only one webhook secret; dual-secret overlap is not implemented.

Telegram `getWebhookInfo` exposes observable webhook fields such as the URL
and allowed updates, but it does not expose or verify the configured secret.
Never treat a matching `getWebhookInfo` result as secret verification. With a
configured secret, backend startup always reapplies it with `setWebhook`,
requires both HTTP success and a root JSON `ok` value of `true`, and fails
startup if registration fails. The `start.sh` Telegram helpers enforce the
same root-`ok` rule, although the normal watcher rollout does not run that
script.

Any future rotation procedure must first implement and review old-plus-next
secret acceptance so Telegram can move between values without an interval in
which valid deliveries are rejected. That overlap is a future design
requirement only; it is not an executable procedure for this release.

Run in **Terminal B — WSL**. First run the complete remote-context preamble at
the end of Section 3, then run this block. It prints only a success marker:

```bash
set -euo pipefail
set +x
cd "$PROD_DIR"
set -a
source "$PROD_DIR/.env"
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
  [[ "$BOOTSTRAP_ADMIN_TELEGRAM_IDS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]]
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
exists or a narrowly controlled bootstrap admin input is present. A nonempty
bootstrap value must have the application's comma-separated positive-integer
shape; invalid or partially ignored input blocks release without printing it.
The `role` column does not exist until the first migration is applied, so run
the aggregate-only durable-admin check in Section 5, not here. Do not record
bootstrap IDs. If bootstrap is needed, the controlled admin must authenticate
after deployment, become durable, and broad bootstrap input must not be left
configured longer than necessary.

When no durable admin exists and bootstrap is used, the operator must privately
confirm the intended controlled identity and enter a non-placeholder,
non-secret release-record reference in `BOOTSTRAP_IDENTITY_CONFIRMATION`.
Neither the confirmation step nor the release record may contain the ID.

## 5. Freeze creates, drain the old backend, and migrate

### LIVE / MANUAL

Schedule a low-traffic window. The 2026-07-07 migration deliberately drops and
recreates `uq_orders_one_active_delivery_per_staff`; index recreation takes a
database lock. Do not apply it during a delivery surge, and do not interrupt or
blindly retry it while DDL is in progress.

In **Terminal A — LOCAL**, source and verify `LOCAL_RELEASE_STATE` as described
in Section 1. Acquire the exclusive release freeze before any production
mutation. The freeze prohibits every other `prod` push, checkout mutation, or
deployment until this release is accepted or rolled back. Pause the watcher
through explicit SSH/WSL context and prove that `prod` has not moved:

```bash
EXCLUSIVE_RELEASE_FREEZE_CONFIRMATION='<exclusive release-freeze record reference>'
case "$EXCLUSIVE_RELEASE_FREEZE_CONFIRMATION" in
  ''|'<exclusive release-freeze record reference>') exit 1 ;;
esac

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

In **Terminal B — WSL**, run the Section 3 remote-context preamble. Create a
temporary Caddyfile and Compose override only in the protected archived state
directory; never edit the production Git checkout's `Caddyfile`. The first
route matches exactly `POST /api/orders` and returns maintenance status 503.
All GETs, Telegram/AliPOS/payment webhook POSTs, and other API routes continue
to the still-running old backend:

```bash
MAINTENANCE_CADDYFILE="$ROLLBACK_DIR/order-create-maintenance.Caddyfile"
MAINTENANCE_OVERRIDE="$ROLLBACK_DIR/order-create-maintenance.yml"

cat > "$MAINTENANCE_CADDYFILE" <<'CADDY'
{
	admin off
	auto_https off
}

http:// {
	encode zstd gzip

	header {
		-Server
		Referrer-Policy strict-origin-when-cross-origin
		X-Content-Type-Options nosniff
	}

	route {
		@order_create {
			method POST
			path /api/orders
		}
		respond @order_create "order creation temporarily unavailable" 503

		respond /healthz "ok" 200
		respond /readyz "ok" 200

		handle /api/* {
			reverse_proxy backend:8000
		}

		handle {
			reverse_proxy frontend:80
		}
	}
}
CADDY

cat > "$MAINTENANCE_OVERRIDE" <<EOF
services:
  caddy:
    volumes:
      - type: bind
        source: $MAINTENANCE_CADDYFILE
        target: /etc/caddy/Caddyfile
        read_only: true
EOF
chmod 600 "$MAINTENANCE_CADDYFILE" "$MAINTENANCE_OVERRIDE"
printf 'MAINTENANCE_CADDYFILE=%q\n' "$MAINTENANCE_CADDYFILE" >> \
  "$ROLLBACK_DIR/release.env"
printf 'MAINTENANCE_OVERRIDE=%q\n' "$MAINTENANCE_OVERRIDE" >> \
  "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PRE_PROD_SOURCE" \
  --env-file "$PROD_DIR/.env" \
  -f "$PRE_PROD_SOURCE/docker-compose.yml" \
  -f "$ROLLBACK_OVERRIDE" \
  -f "$MAINTENANCE_OVERRIDE" \
  config --quiet

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PRE_PROD_SOURCE" \
  --env-file "$PROD_DIR/.env" \
  -f "$PRE_PROD_SOURCE/docker-compose.yml" \
  -f "$ROLLBACK_OVERRIDE" \
  -f "$MAINTENANCE_OVERRIDE" \
  up -d --no-build --force-recreate --no-deps caddy

test "$(docker inspect --format '{{.Id}}' restaurant_backend)" = \
  "$BACKEND_CONTAINER_ID"
test "$(docker inspect --format '{{.Id}}' restaurant_frontend)" = \
  "$FRONTEND_CONTAINER_ID"
test "$(docker inspect --format '{{.Id}}' restaurant_cloudflared)" = \
  "$CLOUDFLARED_CONTAINER_ID"
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = \
  "$POSTGRES_CONTAINER_ID"
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy
test "$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' \
  restaurant_caddy)" = "$MAINTENANCE_CADDYFILE"
```

Verify the local and public create routes return exactly 503, the backend
health route returns 200, and a non-mutating GET to an AliPOS webhook route
returns backend method status 405. These checks retain status codes only:

```bash
set -a
source "$PROD_DIR/.env"
set +a
test -n "${PUBLIC_APP_URL:-}"

test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 -X POST \
  http://127.0.0.1:8080/api/orders)" = 503
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 -X POST \
  "${PUBLIC_APP_URL%/}/api/orders")" = 503
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8080/api/health)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 \
  "${PUBLIC_APP_URL%/}/api/health")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8080/api/webhooks/order-status)" = 405
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 \
  "${PUBLIC_APP_URL%/}/api/webhooks/order-status")" = 405
unset PUBLIC_APP_URL
```

Keep the old backend running for a fixed 600-second drain. This exceeds the
production-base worst-case sequential provider timeout/retry/backoff chain
with margin. New creates remain blocked while callbacks and requests admitted
before the maintenance route can finish:

```bash
DRAIN_STARTED_AT="$(date +%s)"
DRAIN_DEADLINE=$(( DRAIN_STARTED_AT + 600 ))
while [ "$(date +%s)" -lt "$DRAIN_DEADLINE" ]; do
  test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 -X POST \
    http://127.0.0.1:8080/api/orders)" = 503
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 \
    http://127.0.0.1:8080/api/health)" = 200
  sleep 5
done
DRAIN_ELAPSED=$(( $(date +%s) - DRAIN_STARTED_AT ))
test "$DRAIN_ELAPSED" -ge 600
printf 'old_backend_drain_seconds=%s\n' "$DRAIN_ELAPSED"
```

Stop the old backend with the exact 180-second graceful timeout. A timeout,
exit 137, any other signal/forced termination, `OOMKilled=true`, nonzero exit,
nonempty runtime error, or uncertain drain aborts the release. In any such
case keep the maintenance route and freeze active, do not trust either database
gate, and complete provider-side reconciliation before a new attempt:

```bash
if ! docker stop --time 180 restaurant_backend >/dev/null; then
  printf 'old backend did not stop cleanly; release aborted\n' >&2
  exit 1
fi

OLD_BACKEND_STATUS="$(docker inspect --format '{{.State.Status}}' restaurant_backend)"
OLD_BACKEND_OOM="$(docker inspect --format '{{.State.OOMKilled}}' restaurant_backend)"
OLD_BACKEND_EXIT="$(docker inspect --format '{{.State.ExitCode}}' restaurant_backend)"
OLD_BACKEND_ERROR="$(docker inspect --format '{{.State.Error}}' restaurant_backend)"
test "$OLD_BACKEND_STATUS" = exited
test "$OLD_BACKEND_OOM" = false
test "$OLD_BACKEND_EXIT" -eq 0
test -z "$OLD_BACKEND_ERROR"
printf 'old_backend_stop=clean exit_code=0 oom_killed=false\n'
```

Define the compatible-old-backend recovery while Terminal B remains open.
This always keeps the create-maintenance route active and performs no build:

```bash
recover_compatible_old_backend() {
  docker compose \
    --project-name "$COMPOSE_PROJECT_NAME" \
    --project-directory "$PRE_PROD_SOURCE" \
    --env-file "$PROD_DIR/.env" \
    -f "$PRE_PROD_SOURCE/docker-compose.yml" \
    -f "$ROLLBACK_OVERRIDE" \
    up -d --no-build --force-recreate --no-deps backend

  RECOVERY_DEADLINE=$(( $(date +%s) + 600 ))
  while [ "$(date +%s)" -lt "$RECOVERY_DEADLINE" ]; do
    [ "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend 2>/dev/null || true)" = healthy ] && break
    sleep 5
  done
  test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy
  test "$(docker inspect --format '{{.Image}}' restaurant_backend)" = "$BACKEND_IMAGE_ID"
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 -X POST \
    http://127.0.0.1:8080/api/orders)" = 503
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 \
    http://127.0.0.1:8080/api/health)" = 200
}
```

Run the first authoritative legacy-pending gate only now, after create ingress
has been blocked for the full drain and the old backend stopped cleanly. The
query deliberately uses production-base columns only:

```bash
LEGACY_PENDING_BEFORE="$(docker exec -i restaurant_postgres sh -lc \
  'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT count(*)
FROM orders
WHERE discriminator = 'delivery'
  AND payment_method = 'rahmat'
  AND payment_provider = 'multicard'
  AND payment_status = 'pending'
  AND alipos_order_id IS NOT NULL;
SQL
)"
case "$LEGACY_PENDING_BEFORE" in ''|*[!0-9]*) exit 1 ;; esac
if [ "$LEGACY_PENDING_BEFORE" -ne 0 ]; then
  recover_compatible_old_backend
  printf 'release_aborted legacy_pending_before=%s\n' "$LEGACY_PENDING_BEFORE" >&2
  exit 1
fi
printf 'legacy_pending_before=0\n'
```

Do not auto-cancel, charge, or resubmit any matching row. A nonzero count ends
this freeze after the archived old backend is healthy behind the still-active
maintenance route; record the abort and do not continue.

Apply each production migration exactly once, in this order, using the
approved SSH/WSL/PostgreSQL-stdin pattern. These commands send the candidate's
reviewed SQL and print no environment values. The old backend remains stopped:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql \
  database/migrations/2026-07-18-release-safety.sql
do
  ssh restaurant \
    'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
    < "$migration"
done
```

Backfill only the already-created AliPOS rows whose new sync status is null.
Do not broaden this predicate:

```bash
ssh restaurant \
  'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
  <<'SQL'
UPDATE orders
SET alipos_sync_status = 'synced'
WHERE alipos_order_id IS NOT NULL
  AND alipos_sync_status IS NULL;
SQL
```

Run the same exact legacy-pending gate a second time and require zero:

```bash
LEGACY_PENDING_AFTER="$(ssh restaurant \
  'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
  <<'SQL'
SELECT count(*)
FROM orders
WHERE discriminator = 'delivery'
  AND payment_method = 'rahmat'
  AND payment_provider = 'multicard'
  AND payment_status = 'pending'
  AND alipos_order_id IS NOT NULL;
SQL
)"
case "$LEGACY_PENDING_AFTER" in ''|*[!0-9]*) exit 1 ;; esac
test "$LEGACY_PENDING_AFTER" -eq 0
printf 'legacy_pending_after=0\n'
```

If any migration, backfill, or second-gate command fails or the second count is
nonzero, run `recover_compatible_old_backend` in Terminal B, verify its health,
record the aborted freeze, and stop. The migrations are additive, so the
archived old backend is the compatible recovery path. Keep the maintenance
route active; restore normal routing only after either the exact candidate is
healthy or the Section 10 four-service no-build rollback is complete.

Do not run any of these production migrations a second time in this release.
Verify and compare full schema definitions, not names only. The first four
queries output the actual definitions for the release record; the final block
raises an error on a column shape or structural index/constraint mismatch:

```bash
ssh restaurant \
  'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\''' \
  <<'SQL'
SELECT table_name, column_name, data_type, column_default,
       character_maximum_length, numeric_precision, numeric_scale,
       datetime_precision, is_nullable
FROM information_schema.columns
WHERE (table_name = 'users' AND column_name = 'role')
   OR (table_name = 'orders' AND column_name IN (
     'assigned_staff_id', 'assigned_at', 'delivered_at',
     'items_cost', 'delivery_info', 'table_id', 'table_title',
     'hall_id', 'hall_title', 'service_percent',
     'table_access_expires_at', 'alipos_sync_status', 'alipos_sync_error',
     'cancel_requested_at', 'client_request_id',
     'invoice_cancel_status', 'refund_sync_status', 'refund_sync_error',
     'alipos_status_updated_at',
     'alipos_status_check_attempted_at', 'alipos_status_checked_at'
   ))
ORDER BY table_name, column_name;

SELECT conname, pg_get_constraintdef(oid, true) AS constraint_definition
FROM pg_constraint
WHERE conname = 'ck_users_role_valid';

SELECT c.conname, pg_get_constraintdef(c.oid, true) AS constraint_definition
FROM pg_constraint c
JOIN pg_class source_table ON source_table.oid = c.conrelid
WHERE source_table.relname = 'orders'
  AND c.contype = 'f'
  AND pg_get_constraintdef(c.oid, true)
    LIKE 'FOREIGN KEY (assigned_staff_id) REFERENCES users(telegram_id)%';

SELECT indexname, indexdef
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

DO $$
DECLARE
  mismatch_count integer;
BEGIN
  WITH expected(
    table_name, column_name, data_type, nullable, char_length,
    numeric_precision, numeric_scale, datetime_precision, default_kind
  ) AS (VALUES
    ('users', 'role', 'character varying', 'NO', 32, NULL, NULL, NULL, 'customer'),
    ('orders', 'assigned_staff_id', 'bigint', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'assigned_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'delivered_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'items_cost', 'numeric', 'NO', NULL, 12, 2, NULL, 'zero'),
    ('orders', 'delivery_info', 'jsonb', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'table_id', 'uuid', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'table_title', 'character varying', 'YES', 100, NULL, NULL, NULL, 'none'),
    ('orders', 'hall_id', 'uuid', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'hall_title', 'character varying', 'YES', 100, NULL, NULL, NULL, 'none'),
    ('orders', 'service_percent', 'numeric', 'NO', NULL, 5, 2, NULL, 'zero'),
    ('orders', 'table_access_expires_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'alipos_sync_status', 'character varying', 'YES', 32, NULL, NULL, NULL, 'none'),
    ('orders', 'alipos_sync_error', 'text', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'cancel_requested_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'client_request_id', 'uuid', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'invoice_cancel_status', 'character varying', 'YES', 32, NULL, NULL, NULL, 'none'),
    ('orders', 'refund_sync_status', 'character varying', 'YES', 32, NULL, NULL, NULL, 'none'),
    ('orders', 'refund_sync_error', 'text', 'YES', NULL, NULL, NULL, NULL, 'none'),
    ('orders', 'alipos_status_updated_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'alipos_status_check_attempted_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none'),
    ('orders', 'alipos_status_checked_at', 'timestamp without time zone', 'YES', NULL, NULL, NULL, 6, 'none')
  ), actual AS (
    SELECT table_name, column_name, data_type, is_nullable,
           character_maximum_length, numeric_precision, numeric_scale,
           datetime_precision, column_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
  )
  SELECT count(*) INTO mismatch_count
  FROM expected e
  LEFT JOIN actual a USING (table_name, column_name)
  WHERE a.column_name IS NULL
     OR a.data_type <> e.data_type
     OR a.is_nullable <> e.nullable
     OR a.character_maximum_length IS DISTINCT FROM e.char_length
     OR (e.data_type = 'numeric' AND (
       a.numeric_precision IS DISTINCT FROM e.numeric_precision
       OR a.numeric_scale IS DISTINCT FROM e.numeric_scale
     ))
     OR a.datetime_precision IS DISTINCT FROM e.datetime_precision
     OR (e.default_kind = 'none' AND a.column_default IS NOT NULL)
     OR (e.default_kind = 'customer' AND
       a.column_default IS DISTINCT FROM '''customer''::character varying')
     OR (e.default_kind = 'zero' AND
       regexp_replace(coalesce(a.column_default, ''),
         '[()''.:[:space:]]', '', 'g')
         NOT IN ('0', '0numeric'));

  IF mismatch_count <> 0 THEN
    RAISE EXCEPTION 'release column definition mismatch count=%', mismatch_count;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE c.conname = 'ck_users_role_valid'
      AND t.relname = 'users'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid, true) LIKE 'CHECK%'
      AND pg_get_constraintdef(c.oid, true) LIKE '%role%'
      AND pg_get_constraintdef(c.oid, true) LIKE '%customer%'
      AND pg_get_constraintdef(c.oid, true) LIKE '%staff%'
      AND pg_get_constraintdef(c.oid, true) LIKE '%admin%'
  ) THEN
    RAISE EXCEPTION 'role constraint definition mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class source_table ON source_table.oid = c.conrelid
    JOIN pg_namespace source_schema ON source_schema.oid = source_table.relnamespace
    JOIN pg_class target_table ON target_table.oid = c.confrelid
    JOIN pg_namespace target_schema ON target_schema.oid = target_table.relnamespace
    WHERE c.contype = 'f'
      AND source_schema.nspname = 'public'
      AND source_table.relname = 'orders'
      AND target_schema.nspname = 'public'
      AND target_table.relname = 'users'
      AND c.conkey = ARRAY[(
        SELECT attnum
        FROM pg_attribute
        WHERE attrelid = source_table.oid
          AND attname = 'assigned_staff_id'
          AND NOT attisdropped
      )]::smallint[]
      AND c.confkey = ARRAY[(
        SELECT attnum
        FROM pg_attribute
        WHERE attrelid = target_table.oid
          AND attname = 'telegram_id'
          AND NOT attisdropped
      )]::smallint[]
      AND c.confdeltype = 'n'
      AND pg_get_constraintdef(c.oid, true) LIKE '%ON DELETE SET NULL%'
  ) THEN
    RAISE EXCEPTION 'assigned_staff_id foreign key definition mismatch';
  END IF;

  WITH expected(index_name, is_unique, columns, predicate_tokens) AS (VALUES
    ('idx_orders_assigned_staff_id', false, 'assigned_staff_id', NULL),
    ('idx_orders_delivered_at', false, 'delivered_at', NULL),
    ('idx_orders_staff_available', false, 'status, assigned_staff_id, discriminator', NULL),
    ('uq_orders_one_active_delivery_per_staff', true, 'assigned_staff_id',
      'assigned_staff_id|delivery|delivered_at|DELIVERED|CANCELLED|CANCELED'),
    ('idx_orders_table_id', false, 'table_id', NULL),
    ('idx_orders_alipos_sync_status', false, 'alipos_sync_status', NULL),
    ('idx_orders_refund_sync_status', false, 'refund_sync_status', NULL),
    ('uq_orders_user_request', true, 'user_id, client_request_id', 'client_request_id'),
    ('idx_orders_inplace_workspace', false,
      'table_id, alipos_sync_status, status, alipos_status_check_attempted_at',
      'discriminator|inplace')
  ), actual AS (
    SELECT i.relname AS index_name, x.indisunique AS is_unique,
           string_agg(pg_get_indexdef(i.oid, s.n, true), ', ' ORDER BY s.n) AS columns,
           coalesce(pg_get_expr(x.indpred, x.indrelid), '') AS predicate
    FROM pg_index x
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_class t ON t.oid = x.indrelid AND t.relname = 'orders'
    CROSS JOIN LATERAL generate_series(1, x.indnkeyatts) AS s(n)
    WHERE i.relname IN (
      'idx_orders_assigned_staff_id', 'idx_orders_delivered_at',
      'idx_orders_staff_available', 'uq_orders_one_active_delivery_per_staff',
      'idx_orders_table_id', 'idx_orders_alipos_sync_status',
      'idx_orders_refund_sync_status', 'uq_orders_user_request',
      'idx_orders_inplace_workspace'
    )
    GROUP BY i.relname, x.indisunique, x.indpred, x.indrelid
  )
  SELECT count(*) INTO mismatch_count
  FROM expected e
  LEFT JOIN actual a USING (index_name)
  WHERE a.index_name IS NULL
     OR a.is_unique <> e.is_unique
     OR a.columns <> e.columns
     OR (e.predicate_tokens IS NULL AND a.predicate <> '')
     OR (e.predicate_tokens IS NOT NULL AND EXISTS (
       SELECT 1
       FROM unnest(string_to_array(e.predicate_tokens, '|')) token
       WHERE position(token IN a.predicate) = 0
     ));

  IF mismatch_count <> 0 THEN
    RAISE EXCEPTION 'release index definition mismatch count=%', mismatch_count;
  END IF;
END $$;
SQL
```

Compare the emitted defaults, lengths, precision/scale, nullability,
both `pg_get_constraintdef` results, and complete `indexdef` text with all four reviewed
migration files. The catalog assertions are a second executable check, not a
replacement for that comparison. On any mismatch, stop with the watcher
paused. Do not push `prod` or dump data/environments.

Now verify the controlled-admin path after the `role` column exists. In
**Terminal B — WSL**, first run the Section 3 remote-context preamble, then run
this block. It prints only an aggregate count:

```bash
set -a
source "$PROD_DIR/.env"
set +a

BOOTSTRAP_IDENTITY_CONFIRMATION='<non-secret operator confirmation reference>'

if [ -z "${BOOTSTRAP_ADMIN_TELEGRAM_IDS:-}" ]; then
  DURABLE_ADMIN_REQUIRED=1
else
  [[ "$BOOTSTRAP_ADMIN_TELEGRAM_IDS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]]
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

if [ "$DURABLE_ADMIN_COUNT" -eq 0 ] && [ "$DURABLE_ADMIN_REQUIRED" -eq 0 ]; then
  case "$BOOTSTRAP_IDENTITY_CONFIRMATION" in
    ''|'<non-secret operator confirmation reference>') exit 1 ;;
  esac
fi
unset BOOTSTRAP_IDENTITY_CONFIRMATION

printf 'controlled_admin_path=ok durable_admin_count=%s\n' "$DURABLE_ADMIN_COUNT"
```

The old backend remains stopped, the maintenance Caddy remains active, and the
exclusive freeze remains held through the exact-candidate sequence below.

## 6. Push one pinned SHA, wait for exact CI, then start the candidate once

### LOCAL, then LIVE / MANUAL

In **Terminal A — LOCAL**, source and verify `LOCAL_RELEASE_STATE` as described
in Section 1. Recheck the remote and push exactly the clean pinned commit as a
non-force fast-forward. Migration completion is a prerequisite. This is the
only normal production push in the runbook:

```bash
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test -z "$(git status --porcelain)"
git merge-base --is-ancestor "$PRE_PROD_SHA" "$CANDIDATE_SHA"

git push origin "$CANDIDATE_SHA:refs/heads/prod"
```

Discover the exact candidate run with a ten-minute bound, watch it, and assert
each named job separately. `Admin concurrency gate` is mandatory; a broad
backend run that skipped the destructive test is not a substitute:

```bash
REPO=khajiev13/restaurant-mini-app
RUN_DISCOVERY_DEADLINE=$(( $(date +%s) + 600 ))
RUN_ID=''
while [ "$(date +%s)" -lt "$RUN_DISCOVERY_DEADLINE" ]; do
  RUN_ID="$(gh run list \
    --repo "$REPO" \
    --workflow CI \
    --branch prod \
    --event push \
    --limit 100 \
    --json databaseId,headSha \
    --jq "map(select(.headSha == \"$CANDIDATE_SHA\")) \
      | max_by(.databaseId).databaseId // empty")"
  [ -n "$RUN_ID" ] && break
  sleep 10
done
test -n "$RUN_ID"
test "$(gh run view "$RUN_ID" --repo "$REPO" --json headSha --jq .headSha)" = "$CANDIDATE_SHA"
RUN_WAIT_DEADLINE=$(( $(date +%s) + 1800 ))
while :; do
  RUN_STATE="$(gh run view "$RUN_ID" --repo "$REPO" \
    --json headSha,status,conclusion \
    --jq '[.headSha, .status, (.conclusion // "")] | @tsv')"
  IFS=$'\t' read -r RUN_HEAD_SHA RUN_STATUS RUN_CONCLUSION <<< "$RUN_STATE"
  test "$RUN_HEAD_SHA" = "$CANDIDATE_SHA"
  case "$RUN_STATUS" in
    completed) break ;;
    queued|in_progress|pending|requested|waiting) ;;
    *) exit 1 ;;
  esac
  test "$(date +%s)" -lt "$RUN_WAIT_DEADLINE"
  sleep 10
done
test "$RUN_CONCLUSION" = success

for job in 'Backend Tests' 'Admin concurrency gate' 'Frontend Tests'; do
  test "$(gh run view "$RUN_ID" --repo "$REPO" --json jobs \
    --jq "[.jobs[] | select(.name == \"$job\" and .conclusion == \"success\")] | length")" -eq 1
done
```

If CI fails, keep the watcher paused, run `recover_compatible_old_backend` in
Terminal B, and execute the non-force rollback-commit portion of Section 10
before restoring normal routing. Never deploy a different SHA because its CI
happened to be green.

In **Terminal B — WSL**, run the Section 3 remote-context preamble. The watcher
must still be inactive and the maintenance Caddy must still be mounted. Fetch
and cleanly fast-forward the production checkout to the exact CI-approved
candidate without invoking Docker:

```bash
! sudo -n systemctl is-active --quiet deploy-watcher.service
test "$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' \
  restaurant_caddy)" = "$MAINTENANCE_CADDYFILE"
git -C "$PROD_DIR" fetch origin prod
test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$CANDIDATE_SHA"
test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$PRE_PROD_SHA"
test "$(git -C "$PROD_DIR" branch --show-current)" = prod
test -z "$(git -C "$PROD_DIR" status --porcelain)"
git -C "$PROD_DIR" merge --ff-only origin/prod
test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$CANDIDATE_SHA"
```

Validate the exact candidate Compose graph. Require runtime changes, then
build backend and frontend exactly once. A failed or interrupted build aborts
the release; do not retry it in this freeze. Caddy is not part of this build:

```bash
cd "$PROD_DIR"
docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PROD_DIR" \
  --env-file "$PROD_DIR/.env" \
  -f "$PROD_DIR/docker-compose.yml" \
  config --quiet

! git diff --quiet "$PRE_PROD_SHA..$CANDIDATE_SHA" -- \
  backend frontend docker-compose.yml Caddyfile
test -z "${CANDIDATE_BUILD_COMPLETED:-}"
docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PROD_DIR" \
  --env-file "$PROD_DIR/.env" \
  -f "$PROD_DIR/docker-compose.yml" \
  build backend frontend
CANDIDATE_BUILD_COMPLETED=1
printf 'CANDIDATE_BUILD_COMPLETED=1\n' >> "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"
```

Start only the explicitly listed candidate services with `--no-deps` and no
second build. Caddy is deliberately excluded, so `POST /api/orders` remains
503 throughout candidate startup. PostgreSQL must not be recreated:

```bash
docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PROD_DIR" \
  --env-file "$PROD_DIR/.env" \
  -f "$PROD_DIR/docker-compose.yml" \
  up -d --no-build --no-deps backend frontend cloudflared

! sudo -n systemctl is-active --quiet deploy-watcher.service
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = \
  "$POSTGRES_CONTAINER_ID"
test "$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' \
  restaurant_caddy)" = "$MAINTENANCE_CADDYFILE"
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 -X POST \
  http://127.0.0.1:8080/api/orders)" = 503
```

Wait up to 20 minutes for the exact candidate backend and frontend to become
healthy while the maintenance route remains active. Do not restore normal
routing based on checkout state alone:

```bash
DEPLOY_DEADLINE=$(( $(date +%s) + 1200 ))
DEPLOY_READY=0
while [ "$(date +%s)" -lt "$DEPLOY_DEADLINE" ]; do
  BACKEND_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend 2>/dev/null || true)"
  FRONTEND_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend 2>/dev/null || true)"
  CLOUDFLARED_RUNNING="$(docker inspect --format '{{.State.Running}}' restaurant_cloudflared 2>/dev/null || true)"
  MAINTENANCE_MOUNT="$(docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' \
    restaurant_caddy 2>/dev/null || true)"

  if [ "$BACKEND_HEALTH" = healthy ] \
    && [ "$FRONTEND_HEALTH" = healthy ] \
    && [ "$CLOUDFLARED_RUNNING" = true ] \
    && [ "$MAINTENANCE_MOUNT" = "$MAINTENANCE_CADDYFILE" ]; then
    DEPLOY_READY=1
    break
  fi
  sleep 10
done
test "$DEPLOY_READY" -eq 1
test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$CANDIDATE_SHA"
test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$CANDIDATE_SHA"
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = \
  "$POSTGRES_CONTAINER_ID"
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 -X POST \
  http://127.0.0.1:8080/api/orders)" = 503
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8080/api/health)" = 200
```

Only after those candidate health assertions pass, restore the archived normal
Caddy source without a build and without touching dependencies:

```bash
docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PRE_PROD_SOURCE" \
  --env-file "$PROD_DIR/.env" \
  -f "$PRE_PROD_SOURCE/docker-compose.yml" \
  -f "$ROLLBACK_OVERRIDE" \
  up -d --no-build --force-recreate --no-deps caddy

test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy
test "$(docker inspect --format '{{.Image}}' restaurant_caddy)" = "$CADDY_IMAGE_ID"
test "$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' \
  restaurant_caddy)" = "$PRE_PROD_SOURCE/Caddyfile"
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = \
  "$POSTGRES_CONTAINER_ID"
```

Verify local and public health and webhook forwarding before admitting creates.
Then send only an unauthenticated empty JSON request: status 401, 403, or 422
proves the normal route is restored without creating an order; 503 means the
maintenance route is still active and blocks release:

```bash
set -a
source "$PROD_DIR/.env"
set +a
test -n "${PUBLIC_APP_URL:-}"

for base in http://127.0.0.1:8080 "${PUBLIC_APP_URL%/}"; do
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 "$base/healthz")" = 200
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 "$base/api/health")" = 200
  test "$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 \
    "$base/api/webhooks/order-status")" = 405
  NORMAL_POST_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 15 \
    -H 'Content-Type: application/json' -d '{}' "$base/api/orders")"
  case "$NORMAL_POST_STATUS" in 401|403|422) ;; *) exit 1 ;; esac
done
unset PUBLIC_APP_URL NORMAL_POST_STATUS
```

Capture and verify the running candidate application images. Caddy is expected
to remain the archived normal image/source; backend, frontend, and cloudflared
must match the candidate Compose mapping. Assert `http2` without reading the
token-bearing argument:

```bash
NEW_BACKEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_backend)"
NEW_FRONTEND_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_frontend)"
NEW_CADDY_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_caddy)"
NEW_CLOUDFLARED_COMPOSE_IMAGE="$(docker inspect --format '{{.Config.Image}}' restaurant_cloudflared)"
NEW_BACKEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_backend)"
NEW_FRONTEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_frontend)"
NEW_CADDY_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_caddy)"
NEW_CLOUDFLARED_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_cloudflared)"

CANDIDATE_COMPOSE_IMAGES="$(docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PROD_DIR" \
  --env-file "$PROD_DIR/.env" \
  -f "$PROD_DIR/docker-compose.yml" config --images)"
for pair in \
  "$NEW_BACKEND_COMPOSE_IMAGE|$NEW_BACKEND_IMAGE_ID" \
  "$NEW_FRONTEND_COMPOSE_IMAGE|$NEW_FRONTEND_IMAGE_ID" \
  "$NEW_CLOUDFLARED_COMPOSE_IMAGE|$NEW_CLOUDFLARED_IMAGE_ID"
do
  IMAGE_NAME="${pair%%|*}"
  RUNNING_ID="${pair#*|}"
  printf '%s\n' "$CANDIDATE_COMPOSE_IMAGES" | rg -Fx -- "$IMAGE_NAME" >/dev/null
  test "$(docker image inspect --format '{{.Id}}' "$IMAGE_NAME")" = "$RUNNING_ID"
done
unset CANDIDATE_COMPOSE_IMAGES
test "$NEW_BACKEND_IMAGE_ID" != "$BACKEND_IMAGE_ID"
test "$NEW_FRONTEND_IMAGE_ID" != "$FRONTEND_IMAGE_ID"
test "$NEW_CADDY_IMAGE_ID" = "$CADDY_IMAGE_ID"

test "$(docker inspect --format '{{len .Config.Cmd}}' restaurant_cloudflared)" -eq 7
test "$(docker inspect --format '{{index .Config.Cmd 2}}' restaurant_cloudflared)" = --protocol
test "$(docker inspect --format '{{index .Config.Cmd 3}}' restaurant_cloudflared)" = http2
test "$(docker inspect --format '{{index .Config.Cmd 5}}' restaurant_cloudflared)" = --token

for variable in \
  NEW_BACKEND_COMPOSE_IMAGE NEW_FRONTEND_COMPOSE_IMAGE \
  NEW_CADDY_COMPOSE_IMAGE NEW_CLOUDFLARED_COMPOSE_IMAGE \
  NEW_BACKEND_IMAGE_ID NEW_FRONTEND_IMAGE_ID NEW_CADDY_IMAGE_ID \
  NEW_CLOUDFLARED_IMAGE_ID
do
  printf '%s=%q\n' "$variable" "${!variable}"
done >> "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"
```

Resume the watcher only now, after normal routing is verified. Because the
checkout already equals `origin/prod`, the audited watcher must be a strict
no-op. Capture container IDs, observe exactly 60 seconds, and require zero
deployment markers and no replacements:

```bash
test "$WATCHER_EQUAL_SHA_NOOP_AUDITED" -eq 1
for service in backend frontend caddy cloudflared postgres; do
  container="restaurant_$service"
  variable="BEFORE_$(printf '%s' "$service" | tr '[:lower:]' '[:upper:]')_CONTAINER_ID"
  printf -v "$variable" '%s' "$(docker inspect --format '{{.Id}}' "$container")"
done

DEPLOY_WAIT_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sudo -n systemctl start deploy-watcher.service
sudo -n systemctl is-active --quiet deploy-watcher.service

DEPLOY_NOOP_DEADLINE=$(( $(date +%s) + 60 ))
while [ "$(date +%s)" -lt "$DEPLOY_NOOP_DEADLINE" ]; do
  sudo -n systemctl is-active --quiet deploy-watcher.service
  git -C "$PROD_DIR" fetch origin prod
  test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$CANDIDATE_SHA"
  test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$CANDIDATE_SHA"
  sleep 5
done
DEPLOY_WAIT_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

DEPLOY_CYCLES="$(sudo -n journalctl \
  -u deploy-watcher.service \
  --since "$DEPLOY_WAIT_START" \
  --until "$DEPLOY_WAIT_END" \
  --no-pager \
  | awk -v marker="$WATCHER_DEPLOY_MARKER" '
      index($0, marker) { count += 1 }
      END { print count + 0 }
    ')"
test "$DEPLOY_CYCLES" -eq 0

for service in backend frontend caddy cloudflared postgres; do
  container="restaurant_$service"
  variable="BEFORE_$(printf '%s' "$service" | tr '[:lower:]' '[:upper:]')_CONTAINER_ID"
  test "$(docker inspect --format '{{.Id}}' "$container")" = "${!variable}"
done
printf 'watcher_deploy_cycles=%s\n' "$DEPLOY_CYCLES"
```

Any selective build/start failure, candidate health failure, premature Caddy
restoration, nonzero watcher marker, container replacement, wrong checkout
SHA, or failed local/public route check blocks acceptance. Keep the freeze and
maintenance route where possible, then use the compatible-old-backend recovery
or Section 10 four-service no-build rollback before restoring traffic.

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

Run the responsive workspace smoke as the full 3-by-3 matrix below, not one
representative width. For every cell, inspect Tables overview, one table
detail, and browse-only Menu:

| Locale | 320 px | 375 px | 430 px |
| --- | --- | --- | --- |
| English (`en`) | pass/fail | pass/fail | pass/fail |
| Russian (`ru`) | pass/fail | pass/fail | pass/fail |
| Uzbek (`uz`) | pass/fail | pass/fail | pass/fail |

At each width, require no horizontal page scroll, clipped status/price text,
overlap, hidden order boundary, or inaccessible control. Verify toggle,
filters, table rows/cards, refresh, and navigation remain keyboard/touch
reachable with at least 44-by-44-pixel targets. Record only the nine pass/fail
results; screenshots and response/request details remain prohibited.

Browser Network is authoritative for the controlled 403/5xx result. Uvicorn
access-log counts are only an aggregate cross-check.

## 8. Controlled 15-minute watch

### LIVE / MANUAL

Use a stable provider window. In **Terminal B — WSL**, first run the Section 3
remote-context preamble. Do not manufacture a production outage, clear the
directory cache, or induce an empty directory.

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
WATCH_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'WATCH_START=%q\n' "$WATCH_START" >> "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"
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
WATCH_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'WATCH_END=%q\n' "$WATCH_END" >> "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"
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
  /staff_table_status_reconcile/ {
    if (match($0, /staff_table_status_reconcile claimed=[0-9]+ succeeded=[0-9]+ failed=[0-9]+ duration_ms=[0-9]+[[:space:]]*$/)) {
      safe = substr($0, RSTART, RLENGTH)
      sub(/[[:space:]]+$/, "", safe)
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

The sanitizer treats a line as valid only when the safe event ends at the
duration digits, allowing logger-added trailing whitespace only. Any line that
contains the marker but has a missing/reordered field, punctuation, or any
content after the duration increments `reconcile_malformed`; raw malformed
text is never printed.

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

- `PRE_PROD_SHA`, `CANDIDATE_SHA`, the reviewed delta, all three exact green CI
  jobs, the single selective candidate build, and zero watcher deployment
  cycles during equal-SHA resume are recorded.
- Both exact legacy-pending gates returned zero after the clean old-backend
  stop, and the targeted admin-concurrency JUnit totals were `(1,0,0,0)`.
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

- wrong checkout/image, unhealthy service, failed local/public health, any
  watcher deployment cycle during equal-SHA resume, or watcher behavior outside
  its audit;
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

Rollback restores backend, frontend, Caddy configuration, and the cloudflared
`quic` command together from the archived PRE_PROD source. Leave all additive
migration columns, constraints, and indexes in place; schema removal is a
separately reviewed maintenance change.

### LIVE / MANUAL: immediate four-service no-build restore

From **Terminal A — LOCAL**, pause the watcher through explicit SSH/WSL
context before touching containers:

```bash
ssh restaurant 'wsl bash -lc '\''
set -euo pipefail
set +x
sudo -n systemctl stop deploy-watcher.service
! sudo -n systemctl is-active --quiet deploy-watcher.service
'\'''
```

In **Terminal B — WSL**, run the Section 3 remote-context preamble. Verify the
recorded release-boundary SHA shapes, four unique image tags, immutable
archived-source digests, current `.env` link, Compose project, and unchanged
PostgreSQL container. This restore deliberately does not inspect checkout HEAD
or `origin/prod`, because a wrong/stalled checkout is itself a rollback trigger.
Then perform the one incident-only manual recreation:

```bash
for sha in "$PRE_PROD_SHA" "$CANDIDATE_SHA" "$ROLLBACK_COMMIT"; do
  test "${#sha}" -eq 40
  case "$sha" in *[!0-9a-f]*) exit 1 ;; esac
done
test "$(sha256sum "$PRE_PROD_SOURCE/docker-compose.yml" | awk '{print $1}')" = \
  "$PRE_PROD_COMPOSE_SHA256"
test "$(sha256sum "$PRE_PROD_SOURCE/Caddyfile" | awk '{print $1}')" = \
  "$PRE_PROD_CADDY_SHA256"
test "$(readlink -f "$PRE_PROD_SOURCE/.env")" = \
  "$(readlink -f "$PROD_DIR/.env")"
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = "$POSTGRES_CONTAINER_ID"

for pair in \
  "$BACKEND_ROLLBACK_TAG|$BACKEND_IMAGE_ID" \
  "$FRONTEND_ROLLBACK_TAG|$FRONTEND_IMAGE_ID" \
  "$CADDY_ROLLBACK_TAG|$CADDY_IMAGE_ID" \
  "$CLOUDFLARED_ROLLBACK_TAG|$CLOUDFLARED_IMAGE_ID"
do
  TAG="${pair%%|*}"
  IMAGE_ID="${pair#*|}"
  test "$(docker image inspect --format '{{.Id}}' "$TAG")" = "$IMAGE_ID"
done

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$PRE_PROD_SOURCE" \
  --env-file "$PROD_DIR/.env" \
  -f "$PRE_PROD_SOURCE/docker-compose.yml" \
  -f "$ROLLBACK_OVERRIDE" \
  up -d --no-build --force-recreate --no-deps \
  backend frontend caddy cloudflared
```

`--no-deps` excludes PostgreSQL, and all four non-database services are
explicit. Verify exact restored images, Compose labels, health, old Caddy
source behavior, and the `quic` command without reading the token-bearing
argument:

```bash
RESTORE_HEALTH_DEADLINE=$(( $(date +%s) + 600 ))
RESTORE_HEALTH_READY=0
while [ "$(date +%s)" -lt "$RESTORE_HEALTH_DEADLINE" ]; do
  POSTGRES_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_postgres 2>/dev/null || true)"
  BACKEND_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend 2>/dev/null || true)"
  FRONTEND_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend 2>/dev/null || true)"
  CADDY_HEALTH="$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy 2>/dev/null || true)"
  CLOUDFLARED_RUNNING="$(docker inspect --format '{{.State.Running}}' restaurant_cloudflared 2>/dev/null || true)"
  if [ "$POSTGRES_HEALTH" = healthy ] \
    && [ "$BACKEND_HEALTH" = healthy ] \
    && [ "$FRONTEND_HEALTH" = healthy ] \
    && [ "$CADDY_HEALTH" = healthy ] \
    && [ "$CLOUDFLARED_RUNNING" = true ]; then
    RESTORE_HEALTH_READY=1
    break
  fi
  sleep 5
done
test "$RESTORE_HEALTH_READY" -eq 1

for mapping in \
  "backend|restaurant_backend|$BACKEND_IMAGE_ID|$BACKEND_ROLLBACK_TAG" \
  "frontend|restaurant_frontend|$FRONTEND_IMAGE_ID|$FRONTEND_ROLLBACK_TAG" \
  "caddy|restaurant_caddy|$CADDY_IMAGE_ID|$CADDY_ROLLBACK_TAG" \
  "cloudflared|restaurant_cloudflared|$CLOUDFLARED_IMAGE_ID|$CLOUDFLARED_ROLLBACK_TAG"
do
  SERVICE_NAME="${mapping%%|*}"
  REST="${mapping#*|}"
  CONTAINER_NAME="${REST%%|*}"
  REST="${REST#*|}"
  EXPECTED_ID="${REST%%|*}"
  EXPECTED_NAME="${REST#*|}"
  test "$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")" = "$EXPECTED_ID"
  test "$(docker inspect --format '{{.Config.Image}}' "$CONTAINER_NAME")" = "$EXPECTED_NAME"
  test "$(docker inspect --format \
    '{{index .Config.Labels "com.docker.compose.project"}}' "$CONTAINER_NAME")" = \
    "$COMPOSE_PROJECT_NAME"
  test "$(docker inspect --format \
    '{{index .Config.Labels "com.docker.compose.service"}}' "$CONTAINER_NAME")" = \
    "$SERVICE_NAME"
done

test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_postgres)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy
test "$(docker inspect --format '{{.State.Running}}' restaurant_cloudflared)" = true
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = "$POSTGRES_CONTAINER_ID"
test "$(docker inspect --format '{{len .Config.Cmd}}' restaurant_cloudflared)" -eq 7
test "$(docker inspect --format '{{index .Config.Cmd 2}}' restaurant_cloudflared)" = --protocol
test "$(docker inspect --format '{{index .Config.Cmd 3}}' restaurant_cloudflared)" = quic
test "$(docker inspect --format '{{index .Config.Cmd 5}}' restaurant_cloudflared)" = --token

curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/healthz >/dev/null
curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/api/health >/dev/null
set -a
source "$PROD_DIR/.env"
set +a
test -n "${PUBLIC_APP_URL:-}"
curl -fsS --connect-timeout 5 --max-time 15 "${PUBLIC_APP_URL%/}/healthz" >/dev/null
curl -fsS --connect-timeout 5 --max-time 15 "${PUBLIC_APP_URL%/}/api/health" >/dev/null
unset PUBLIC_APP_URL
```

### LOCAL: push only the pre-created exact rollback SHA

In **Terminal A — LOCAL**, source and verify `LOCAL_RELEASE_STATE`. Do not
create another commit, reset, or force-push. Re-verify the recorded object's
tree and parent, ensure remote `prod` is exactly the candidate, then push the
pre-created non-force fast-forward rollback SHA:

```bash
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$CANDIDATE_SHA"
test "$(git rev-parse "$ROLLBACK_COMMIT^{tree}")" = \
  "$(git rev-parse "$PRE_PROD_SHA^{tree}")"
test "$(git rev-parse "$ROLLBACK_COMMIT^1")" = "$CANDIDATE_SHA"
git merge-base --is-ancestor "$CANDIDATE_SHA" "$ROLLBACK_COMMIT"

git push origin "$ROLLBACK_COMMIT:refs/heads/prod"
```

Keep the watcher paused. Discover only the rollback SHA's own `CI` push run
with a ten-minute bound, watch it, and independently assert both named jobs:

```bash
REPO=khajiev13/restaurant-mini-app
ROLLBACK_RUN_DISCOVERY_DEADLINE=$(( $(date +%s) + 600 ))
ROLLBACK_RUN_ID=''
while [ "$(date +%s)" -lt "$ROLLBACK_RUN_DISCOVERY_DEADLINE" ]; do
  ROLLBACK_RUN_ID="$(gh run list \
    --repo "$REPO" \
    --workflow CI \
    --branch prod \
    --event push \
    --limit 100 \
    --json databaseId,headSha \
    --jq "map(select(.headSha == \"$ROLLBACK_COMMIT\")) \
      | max_by(.databaseId).databaseId // empty")"
  [ -n "$ROLLBACK_RUN_ID" ] && break
  sleep 10
done
test -n "$ROLLBACK_RUN_ID"
test "$(gh run view "$ROLLBACK_RUN_ID" --repo "$REPO" \
  --json headSha --jq .headSha)" = "$ROLLBACK_COMMIT"
ROLLBACK_RUN_WAIT_DEADLINE=$(( $(date +%s) + 1800 ))
while :; do
  ROLLBACK_RUN_STATE="$(gh run view "$ROLLBACK_RUN_ID" --repo "$REPO" \
    --json headSha,status,conclusion \
    --jq '[.headSha, .status, (.conclusion // "")] | @tsv')"
  IFS=$'\t' read -r ROLLBACK_RUN_HEAD_SHA ROLLBACK_RUN_STATUS \
    ROLLBACK_RUN_CONCLUSION <<< "$ROLLBACK_RUN_STATE"
  test "$ROLLBACK_RUN_HEAD_SHA" = "$ROLLBACK_COMMIT"
  case "$ROLLBACK_RUN_STATUS" in
    completed) break ;;
    queued|in_progress|pending|requested|waiting) ;;
    *) exit 1 ;;
  esac
  test "$(date +%s)" -lt "$ROLLBACK_RUN_WAIT_DEADLINE"
  sleep 10
done
test "$ROLLBACK_RUN_CONCLUSION" = success

for job in 'Backend Tests' 'Frontend Tests'; do
  test "$(gh run view "$ROLLBACK_RUN_ID" --repo "$REPO" --json jobs \
    --jq "[.jobs[] | select(.name == \"$job\" and .conclusion == \"success\")] | length")" -eq 1
done
```

If rollback CI fails, leave the four-service no-build restore running and the
watcher paused; escalate rather than deploying an unapproved SHA.

### LIVE / MANUAL: fast-forward checkout and resume as an audited no-op

Keep the watcher paused after rollback CI. In **Terminal B — WSL**, rerun the
Section 3 remote-context preamble. Without running Docker or Compose, fetch and
cleanly fast-forward the production checkout to the pre-created rollback
commit. Then prove the tree is PRE_PROD and the four containers still run the
immutable images restored by the incident-only no-build command:

```bash
! sudo -n systemctl is-active --quiet deploy-watcher.service
test "$WATCHER_EQUAL_SHA_NOOP_AUDITED" -eq 1
test -z "$(git -C "$PROD_DIR" status --porcelain)"
test "$(git -C "$PROD_DIR" branch --show-current)" = prod
git -C "$PROD_DIR" fetch origin prod
test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$ROLLBACK_COMMIT"
git -C "$PROD_DIR" merge --ff-only origin/prod
test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$ROLLBACK_COMMIT"
test "$(git -C "$PROD_DIR" rev-parse 'HEAD^{tree}')" = \
  "$(git -C "$PROD_DIR" rev-parse "$PRE_PROD_SHA^{tree}")"
test "$(git -C "$PROD_DIR" rev-parse "$ROLLBACK_COMMIT^1")" = "$CANDIDATE_SHA"

for pair in \
  "restaurant_backend|$BACKEND_IMAGE_ID" \
  "restaurant_frontend|$FRONTEND_IMAGE_ID" \
  "restaurant_caddy|$CADDY_IMAGE_ID" \
  "restaurant_cloudflared|$CLOUDFLARED_IMAGE_ID"
do
  CONTAINER_NAME="${pair%%|*}"
  EXPECTED_IMAGE_ID="${pair#*|}"
  test "$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")" = \
    "$EXPECTED_IMAGE_ID"
done
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = "$POSTGRES_CONTAINER_ID"

ROLLBACK_NOOP_WAIT_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'ROLLBACK_NOOP_WAIT_START=%q\n' "$ROLLBACK_NOOP_WAIT_START" >> \
  "$ROLLBACK_DIR/release.env"
chmod 600 "$ROLLBACK_DIR/release.env"
```

From **Terminal A — LOCAL**, resume the WSL watcher only after the manual
fast-forward. The same handoff independently reloads protected state, fetches
`prod`, proves `HEAD == origin/prod == ROLLBACK_COMMIT`, and requires the
audited equal-SHA no-op flag before starting:

```bash
ssh restaurant 'wsl bash -s' <<'WSL'
set -euo pipefail
set +x
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/restaurant-mini-app/rollbacks"
source "$STATE_ROOT/current-staff-tables.env"
source "$ROLLBACK_DIR/release.env"
test "$WATCHER_EQUAL_SHA_NOOP_AUDITED" -eq 1
! sudo -n systemctl is-active --quiet deploy-watcher.service
git -C "$PROD_DIR" fetch origin prod
test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$ROLLBACK_COMMIT"
test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$ROLLBACK_COMMIT"
sudo -n systemctl start deploy-watcher.service
sudo -n systemctl is-active --quiet deploy-watcher.service
WSL
```

In **Terminal B — WSL**, rerun the remote-context preamble. Observe the watcher
for exactly 60 seconds. Any SHA drift, image replacement, inactive watcher, or
deployment marker stops the watcher and blocks the release:

```bash
test -n "$ROLLBACK_NOOP_WAIT_START"

rollback_noop_fail() {
  sudo -n systemctl stop deploy-watcher.service
  printf 'rollback watcher no-op verification failed\n' >&2
  exit 1
}

ROLLBACK_NOOP_DEADLINE=$(( $(date +%s) + 60 ))
while [ "$(date +%s)" -lt "$ROLLBACK_NOOP_DEADLINE" ]; do
  sudo -n systemctl is-active --quiet deploy-watcher.service || rollback_noop_fail
  git -C "$PROD_DIR" fetch origin prod || rollback_noop_fail
  test "$(git -C "$PROD_DIR" rev-parse HEAD)" = "$ROLLBACK_COMMIT" || rollback_noop_fail
  test "$(git -C "$PROD_DIR" rev-parse origin/prod)" = "$ROLLBACK_COMMIT" || rollback_noop_fail
  for pair in \
    "restaurant_backend|$BACKEND_IMAGE_ID" \
    "restaurant_frontend|$FRONTEND_IMAGE_ID" \
    "restaurant_caddy|$CADDY_IMAGE_ID" \
    "restaurant_cloudflared|$CLOUDFLARED_IMAGE_ID"
  do
    CONTAINER_NAME="${pair%%|*}"
    EXPECTED_IMAGE_ID="${pair#*|}"
    test "$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")" = \
      "$EXPECTED_IMAGE_ID" || rollback_noop_fail
  done
  sleep 5
done

ROLLBACK_NOOP_WAIT_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if ! ROLLBACK_DEPLOY_CYCLES="$(sudo -n journalctl \
  -u deploy-watcher.service \
  --since "$ROLLBACK_NOOP_WAIT_START" \
  --until "$ROLLBACK_NOOP_WAIT_END" \
  --no-pager \
  | awk -v marker="$WATCHER_DEPLOY_MARKER" '
      index($0, marker) { count += 1 }
      END { print count + 0 }
    ')"; then
  rollback_noop_fail
fi
test "$ROLLBACK_DEPLOY_CYCLES" -eq 0 || rollback_noop_fail

for pair in \
  "restaurant_backend|$BACKEND_IMAGE_ID" \
  "restaurant_frontend|$FRONTEND_IMAGE_ID" \
  "restaurant_caddy|$CADDY_IMAGE_ID" \
  "restaurant_cloudflared|$CLOUDFLARED_IMAGE_ID"
do
  CONTAINER_NAME="${pair%%|*}"
  EXPECTED_IMAGE_ID="${pair#*|}"
  test "$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")" = \
    "$EXPECTED_IMAGE_ID" || rollback_noop_fail
done
test "$(docker inspect --format '{{.Id}}' restaurant_postgres)" = \
  "$POSTGRES_CONTAINER_ID" || rollback_noop_fail
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_backend)" = healthy || rollback_noop_fail
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend)" = healthy || rollback_noop_fail
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy || rollback_noop_fail
test "$(docker inspect --format '{{.State.Running}}' restaurant_cloudflared)" = true || rollback_noop_fail
test "$(docker inspect --format '{{index .Config.Cmd 3}}' restaurant_cloudflared)" = quic || rollback_noop_fail

curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/healthz >/dev/null || rollback_noop_fail
curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/api/health >/dev/null || rollback_noop_fail
set -a
source "$PROD_DIR/.env"
set +a
curl -fsS --connect-timeout 5 --max-time 15 "${PUBLIC_APP_URL%/}/healthz" >/dev/null || rollback_noop_fail
curl -fsS --connect-timeout 5 --max-time 15 "${PUBLIC_APP_URL%/}/api/health" >/dev/null || rollback_noop_fail
unset PUBLIC_APP_URL
printf 'rollback_watcher_deploy_cycles=%s\n' "$ROLLBACK_DEPLOY_CYCLES"
```

This release permits exactly one selective backend/frontend build while the
watcher is stopped and, only during an incident, one manual four-service
`--no-build` restore. It never permits a watcher or rollback rebuild. If
equal-SHA no-op behavior, the manual fast-forward, exact image preservation, or
zero marker count cannot be proven, stop and leave the watcher paused until a
separately reviewed rollback mode exists.

## Release record checklist

- [ ] Clean pinned `PRE_PROD_SHA`, `MAIN_SHA`, sibling SHA, and `CANDIDATE_SHA`
- [ ] Full `origin/prod..CANDIDATE_SHA` review approval
- [ ] Complete local backend, Ruff, frontend, build, Pandoc, static, and migration-twice gates
- [ ] Classic `repo` scope plus ADMIN viewer authority proved privately before accepting protection 404; zero applicable rules verified
- [ ] Exact-SHA watcher gate and explicit direct-release authorization recorded
- [ ] Exclusive release freeze recorded before create maintenance and held through acceptance or rollback
- [ ] Watcher working directory, pause/resume, marker, and equal-SHA zero-marker no-op verified
- [ ] Staff take ordering proved as `8s < 10s < 15s < deployed proxy timeout`; every proxy layer has a non-secret evidence reference
- [ ] Pre-created rollback SHA tree/parent and both non-force dry-run paths verified
- [ ] External mode-700 rollback state, PRE source, exact Compose project, four image mappings/tags, and four-service no-build dry run verified
- [ ] Secret shape, controlled admin path, and default-false online gate verified without values
- [ ] Production Telegram token and webhook secret stayed frozen; no rotation was attempted and `getWebhookInfo` was not treated as secret verification
- [ ] Maintenance Caddy blocked exactly `POST /api/orders`; old backend drained 600 seconds and stopped cleanly within the 180-second timeout
- [ ] Both exact legacy-pending gates returned zero; four production migrations and the narrow sync-status backfill ran before `prod` push
- [ ] Exact candidate's three CI jobs were green; one selective app build ran with Caddy excluded; candidate health and SHA were verified before normal Caddy restoration
- [ ] Incident path, if used, performed one four-service no-build restore, manual rollback fast-forward, zero-marker watcher no-op, and no rollback rebuild
- [ ] Customer 403 and controlled staff/admin 200/privacy/read-only smokes passed
- [ ] Responsive Tables/detail/Menu matrix passed at 320/375/430 px in en/ru/uz
- [ ] Stable 15-minute watch met every numeric threshold
- [ ] No raw logs, URLs, headers, bodies, business IDs, tokens, or unsafe screenshots retained
