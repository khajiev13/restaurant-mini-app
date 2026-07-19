# Production Webhook Startup Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release the exact current production functionality with a single-owner Telegram webhook startup phase, restore `restaurant_backend`, and preserve every healthy production service.

**Architecture:** Extract Telegram registration into one service, invoke it once from a container entrypoint, then `exec` the unchanged two-worker Uvicorn command. Publish a candidate based on `ccaa757`, prepare a non-force rollback commit and immutable `81489d1` fallback image, and recreate only the backend while the Windows supervisor task is paused.

**Tech Stack:** Python 3.12, FastAPI, HTTPX, Uvicorn, pytest, Ruff, Docker Compose, PostgreSQL 16, Windows Task Scheduler, WSL2, GitHub Actions.

## Global Constraints

- Release base: `ccaa757e49b83b4024d34c42ef4e5d07a3caa467`.
- Fallback source: `81489d12bdf717bd05e993419ba53a2e3a4e32df`.
- Exclude `527d3c975ae5f2049d216e7808e78b3ea9faeebc` and every numeric table/QR branch commit.
- Do not add/change migrations, frontend behavior, secrets, ports, Compose dependencies, or the two-worker setting.
- Do not rebuild/recreate PostgreSQL, frontend, Caddy, Cloudflare, or BitAgent.
- Automated tests must not call Telegram or use production credentials.
- Never expose tokens, secrets, JWTs, headers, provider bodies, customer data, or business identifiers.
- The host controller is `\RestaurantWSLApps` plus `/usr/local/sbin/restaurant-stack-supervisor.sh`; systemd is not available.
- Pin every Git SHA and image ID. Never force-push `prod`, delete a volume, or rebuild during rollback.

---

### Task 1: Create the isolated exact-base candidate

**Files:**
- Reference: `docs/superpowers/specs/2026-07-18-production-webhook-startup-recovery-design.md`

**Interfaces:**
- Consumes: exact `origin/prod` base.
- Produces: clean `codex/production-webhook-startup-recovery` worktree with only the approved spec.

- [ ] **Step 1: Use the worktree workflow**

Invoke `superpowers:using-git-worktrees`, using:

```text
/Users/khajievroma/Projects/restaurant-mini-app/.worktrees/production-webhook-startup-recovery
```

- [ ] **Step 2: Pin and validate the base**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
git fetch --prune origin
test "$(git rev-parse origin/prod)" = ccaa757e49b83b4024d34c42ef4e5d07a3caa467
git merge-base --is-ancestor origin/main origin/prod
git merge-base --is-ancestor origin/codex/alipos-inplace-total-fix origin/prod
! git merge-base --is-ancestor 527d3c975ae5f2049d216e7808e78b3ea9faeebc origin/prod
```

- [ ] **Step 3: Create the worktree and carry the approved spec**

```bash
git worktree add /Users/khajievroma/Projects/restaurant-mini-app/.worktrees/production-webhook-startup-recovery -b codex/production-webhook-startup-recovery origin/prod
cd /Users/khajievroma/Projects/restaurant-mini-app/.worktrees/production-webhook-startup-recovery
git cherry-pick ccfd5d5 3c7f820 cacb3e7
test -z "$(git status --porcelain)"
test "$(git diff --name-only origin/prod...HEAD)" = docs/superpowers/specs/2026-07-18-production-webhook-startup-recovery-design.md
```

---

### Task 2: Extract registration without changing behavior

**Files:**
- Create: `backend/app/services/telegram_webhook_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/api/test_webhooks.py`

**Interfaces:**
- Consumes: `settings` and `httpx.AsyncClient`.
- Produces: `async register_telegram_webhook() -> None`; FastAPI temporarily remains its caller.

- [ ] **Step 1: Point existing tests at the new module**

Change the test import to:

```python
from app.services.telegram_webhook_service import register_telegram_webhook
```

Change all HTTPX patch targets to:

```text
app.services.telegram_webhook_service.httpx.AsyncClient
```

Change registration `caplog` logger values to:

```text
app.services.telegram_webhook_service
```

- [ ] **Step 2: Prove the new module is missing**

```bash
cd backend
/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python -m pytest tests/api/test_webhooks.py -k register_telegram_webhook -q
```

Expected: `ModuleNotFoundError` for `app.services.telegram_webhook_service`.

- [ ] **Step 3: Create the service**

Create `backend/app/services/telegram_webhook_service.py`:

```python
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
TELEGRAM_ALLOWED_UPDATES = ["message"]


async def _get_telegram_webhook_info(
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    response = await client.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo",
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("telegram_get_webhook_info_api_rejected")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("telegram_get_webhook_info_invalid_result")
    return result


def _normalized_allowed_updates(values: list[str] | None) -> list[str]:
    return sorted(values or [])


async def register_telegram_webhook() -> None:
    if not settings.public_base_url or not settings.telegram_bot_token:
        return

    webhook_url = f"{settings.public_base_url}/api/webhooks/bot"
    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": TELEGRAM_ALLOWED_UPDATES,
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    has_configured_secret = bool(settings.telegram_webhook_secret)
    try:
        async with httpx.AsyncClient() as client:
            if not has_configured_secret:
                try:
                    current_info = await _get_telegram_webhook_info(client)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "telegram_webhook_inspection_failed category=request_or_response"
                    )
                else:
                    current_url = current_info.get("url", "")
                    current_updates = _normalized_allowed_updates(
                        current_info.get("allowed_updates")
                    )
                    expected_updates = _normalized_allowed_updates(
                        TELEGRAM_ALLOWED_UPDATES
                    )
                    if current_url == webhook_url and current_updates == expected_updates:
                        logger.info(
                            "Telegram webhook already configured for %s; skipping setWebhook",
                            webhook_url,
                        )
                        return

            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            response_payload = response.json()
            if (
                not isinstance(response_payload, dict)
                or response_payload.get("ok") is not True
            ):
                raise RuntimeError("telegram_set_webhook_api_rejected")
    except Exception:  # noqa: BLE001
        category = "configured_secret" if has_configured_secret else "empty_secret"
        logger.warning(
            "telegram_webhook_registration_failed category=%s",
            category,
        )
        if has_configured_secret:
            raise RuntimeError("telegram_webhook_registration_failed") from None
        return

    logger.info("Telegram webhook registered for %s", webhook_url)
```

- [ ] **Step 4: Preserve the existing startup call through the service**

In `backend/app/main.py`, remove `Any`, `httpx`, `TELEGRAM_ALLOWED_UPDATES`, and the three webhook functions. Add:

```python
from app.services.telegram_webhook_service import register_telegram_webhook
```

Immediately after constructing `app`, add:

```python
app.add_event_handler("startup", register_telegram_webhook)
```

- [ ] **Step 5: Verify and commit**

```bash
cd backend
/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python -m pytest tests/api/test_webhooks.py -k register_telegram_webhook -q
cd ..
git add backend/app/main.py backend/app/services/telegram_webhook_service.py backend/tests/api/test_webhooks.py
git commit -m "refactor: isolate Telegram webhook registration"
```

---

### Task 3: Give registration one container owner

**Files:**
- Create: `backend/app/container_entrypoint.py`
- Create: `backend/tests/test_container_entrypoint.py`
- Modify: `backend/app/main.py`
- Modify: `backend/Dockerfile`

**Interfaces:**
- Consumes: `register_telegram_webhook()`.
- Produces: `main() -> None` that registers once then process-replaces itself with two-worker Uvicorn.

- [ ] **Step 1: Write failing entrypoint tests**

Create `backend/tests/test_container_entrypoint.py`:

```python
from pathlib import Path

import pytest

from app import container_entrypoint
from app.main import app
from app.services.telegram_webhook_service import register_telegram_webhook

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_entrypoint_registers_once_before_exec(monkeypatch):
    events: list[object] = []

    async def register_once() -> None:
        events.append("register")

    def exec_once(executable: str, argv: list[str]) -> None:
        events.append((executable, argv))
        raise SystemExit(0)

    monkeypatch.setattr(container_entrypoint, "register_telegram_webhook", register_once)
    monkeypatch.setattr(container_entrypoint.os, "execvp", exec_once)
    with pytest.raises(SystemExit, match="0"):
        container_entrypoint.main()
    assert events == ["register", ("uvicorn", container_entrypoint.UVICORN_COMMAND)]


def test_entrypoint_does_not_exec_after_registration_failure(monkeypatch):
    async def fail_registration() -> None:
        raise RuntimeError("telegram_webhook_registration_failed")

    def unexpected_exec(_executable: str, _argv: list[str]) -> None:
        pytest.fail("Uvicorn must not start")

    monkeypatch.setattr(
        container_entrypoint,
        "register_telegram_webhook",
        fail_registration,
    )
    monkeypatch.setattr(container_entrypoint.os, "execvp", unexpected_exec)
    with pytest.raises(RuntimeError, match="telegram_webhook_registration_failed"):
        container_entrypoint.main()


def test_fastapi_workers_do_not_register_telegram_webhook():
    assert register_telegram_webhook not in app.router.on_startup


def test_dockerfile_uses_single_owner_entrypoint():
    source = DOCKERFILE.read_text()
    assert 'CMD ["python", "-m", "app.container_entrypoint"]' in source
    assert 'CMD ["uvicorn"' not in source
```

- [ ] **Step 2: Prove the entrypoint is missing**

```bash
cd backend
/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python -m pytest tests/test_container_entrypoint.py -q
```

Expected: import failure for `app.container_entrypoint`.

- [ ] **Step 3: Implement the entrypoint**

Create `backend/app/container_entrypoint.py`:

```python
import asyncio
import os

from app.services.telegram_webhook_service import register_telegram_webhook

UVICORN_COMMAND = [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--workers",
    "2",
    "--proxy-headers",
    "--forwarded-allow-ips=*",
]


def main() -> None:
    asyncio.run(register_telegram_webhook())
    os.execvp(UVICORN_COMMAND[0], UVICORN_COMMAND)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Remove worker ownership and change only the image command**

Remove the webhook service import and `app.add_event_handler` from `backend/app/main.py`. Replace the Dockerfile `CMD` with:

```dockerfile
CMD ["python", "-m", "app.container_entrypoint"]
```

- [ ] **Step 5: Verify and commit**

```bash
cd backend
/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python -m pytest tests/test_container_entrypoint.py -q
/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python -m pytest tests/api/test_webhooks.py -k register_telegram_webhook -q
cd ..
git add backend/Dockerfile backend/app/container_entrypoint.py backend/app/main.py backend/tests/test_container_entrypoint.py
git commit -m "fix: register Telegram webhook before worker fork"
```

---

### Task 4: Prove the complete candidate locally

**Files:**
- Verify: all candidate files and repository test suites.

**Interfaces:**
- Consumes: Task 3 branch.
- Produces: clean candidate SHA and inspected local backend image.

- [ ] **Step 1: Run the complete backend gate**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/.worktrees/production-webhook-startup-recovery
set -a
source /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
BACKEND_PYTHON=/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python
test -x "$BACKEND_PYTHON"
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=55432 "$BACKEND_PYTHON" -m pytest -q --tb=short
"$BACKEND_PYTHON" -m ruff check .
cd ..
```

Expected: full pytest and Ruff pass without a live Telegram call.

- [ ] **Step 2: Run the complete frontend gate**

```bash
cd frontend
npm ci --legacy-peer-deps
npm test
npm run typecheck
npm run lint
npm run build
cd ..
```

Expected: every command passes and no frontend file changes.

- [ ] **Step 3: Validate Compose and the built command**

```bash
docker compose config --quiet
CANDIDATE_SHA="$(git rev-parse HEAD)"
docker build --label "org.opencontainers.image.revision=$CANDIDATE_SHA" --tag restaurant-mini-app-backend:local-webhook-recovery backend
test "$(docker image inspect --format '{{json .Config.Cmd}}' restaurant-mini-app-backend:local-webhook-recovery)" = '["python","-m","app.container_entrypoint"]'
test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' restaurant-mini-app-backend:local-webhook-recovery)" = "$CANDIDATE_SHA"
```

- [ ] **Step 4: Review and pin the delta**

```bash
git diff --check origin/prod...HEAD
git log --reverse --oneline origin/prod..HEAD
git diff --name-status origin/prod...HEAD
test -z "$(git status --porcelain)"
! git merge-base --is-ancestor 527d3c975ae5f2049d216e7808e78b3ea9faeebc HEAD
test -z "$(git diff --name-only origin/prod...HEAD -- frontend database)"
```

Expected code paths:

```text
backend/Dockerfile
backend/app/container_entrypoint.py
backend/app/main.py
backend/app/services/telegram_webhook_service.py
backend/tests/api/test_webhooks.py
backend/tests/test_container_entrypoint.py
```

The approved design specification is the only documentation change.

---

### Task 5: Prepare rollback Git, publish `prod`, and require exact-SHA CI

**Files:**
- Git refs only.

**Interfaces:**
- Consumes: clean candidate from Task 4.
- Produces: rollback commit with the exact `81489d1` tree, updated `origin/prod`, and successful exact-SHA CI.

- [ ] **Step 1: Recheck the remote boundary**

```bash
git fetch --prune origin
PRE_PROD_SHA="$(git rev-parse origin/prod)"
CANDIDATE_SHA="$(git rev-parse HEAD)"
FALLBACK_SHA=81489d12bdf717bd05e993419ba53a2e3a4e32df
test "$PRE_PROD_SHA" = ccaa757e49b83b4024d34c42ef4e5d07a3caa467
git merge-base --is-ancestor "$PRE_PROD_SHA" "$CANDIDATE_SHA"
test -z "$(git status --porcelain)"
```

- [ ] **Step 2: Create the non-force rollback commit**

```bash
ROLLBACK_COMMIT="$(git commit-tree "$FALLBACK_SHA^{tree}" -p "$CANDIDATE_SHA" -m "revert: restore pre-recovery restaurant backend source")"
test "$(git rev-parse "$ROLLBACK_COMMIT^{tree}")" = "$(git rev-parse "$FALLBACK_SHA^{tree}")"
test "$(git rev-parse "$ROLLBACK_COMMIT^1")" = "$CANDIDATE_SHA"
git update-ref refs/heads/codex/production-webhook-startup-recovery-rollback "$ROLLBACK_COMMIT"
```

- [ ] **Step 3: Push without force**

```bash
git push -u origin codex/production-webhook-startup-recovery
git push -u origin codex/production-webhook-startup-recovery-rollback
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$PRE_PROD_SHA"
git push origin "$CANDIDATE_SHA:refs/heads/prod"
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$CANDIDATE_SHA"
```

- [ ] **Step 4: Require the exact GitHub Actions run**

Poll the public GitHub Actions API for at most ten minutes:

```bash
python3 - "$CANDIDATE_SHA" <<'PY'
import json
import sys
import urllib.request

candidate = sys.argv[1]
base = "https://api.github.com/repos/khajiev13/restaurant-mini-app"
headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "codex-release-check",
}
request = urllib.request.Request(
    f"{base}/actions/runs?head_sha={candidate}&event=push",
    headers=headers,
)
with urllib.request.urlopen(request, timeout=15) as response:
    runs = json.load(response)["workflow_runs"]
matches = [
    item
    for item in runs
    if item["head_sha"] == candidate and item["name"] == "CI"
]
if not matches or matches[0]["status"] != "completed":
    print(f"ci_pending exact_sha={candidate}")
    raise SystemExit(75)
run = matches[0]
if run["conclusion"] != "success":
    raise SystemExit(f"exact candidate CI failed: {run['conclusion']}")

request = urllib.request.Request(run["jobs_url"], headers=headers)
with urllib.request.urlopen(request, timeout=15) as response:
    jobs = json.load(response)["jobs"]
required = {"Backend Tests", "Admin concurrency gate", "Frontend Tests"}
successful = {job["name"] for job in jobs if job["conclusion"] == "success"}
if not required.issubset(successful):
    raise SystemExit(f"missing successful jobs: {sorted(required - successful)}")
print(f"ci_run_id={run['id']} exact_sha={candidate} required_jobs=3")
PY
```

This script is one bounded snapshot. If it exits `75`, wait 15 seconds through the execution environment's non-blocking wait mechanism, send progress before 60 seconds elapse, and rerun it. Stop after ten minutes. Never accept another SHA's run.

If exact-SHA CI fails, do not touch the server checkout or containers. Fix, retest, create a new rollback commit whose parent is the new candidate, and repeat this task.

---

### Task 6: Freeze the host boundary and deploy only the backend

**Files:**
- Read/deploy: `/home/khajiev13/apps/restaurant-mini-app`.
- Create on host: mode-700 release directory below `/root/.local/state/restaurant-mini-app/`.
- Create on host: mode-600 `release.env` containing only SHAs and image/container IDs.

**Interfaces:**
- Consumes: exact green candidate and prepared rollback ref.
- Produces: stopped immutable fallback image, healthy candidate backend, resumed supervisor, and verified production stability.

- [ ] **Step 1: Confirm and pause only the scheduled supervisor**

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant hostname
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app rev-parse HEAD'
ssh restaurant 'wsl.exe -d Ubuntu -u root -- pgrep -fc "^bash /usr/local/sbin/restaurant-stack-supervisor.sh$"'
ssh restaurant 'schtasks.exe /Change /TN "\RestaurantWSLApps" /Disable'
ssh restaurant 'schtasks.exe /End /TN "\RestaurantWSLApps"'
```

Expected before pause: host `admin`, source `81489d12bdf717bd05e993419ba53a2e3a4e32df`, and one supervisor. Poll the targeted `pgrep` until it returns `0`. Do not stop WSL, Docker, or any healthy service.

- [ ] **Step 2: Enter one root WSL cutover shell and pin state**

```bash
ssh -tt restaurant 'wsl.exe -d Ubuntu -u root'
```

Inside WSL:

```bash
set -euo pipefail
set +x
umask 077
PROD_DIR=/home/khajiev13/apps/restaurant-mini-app
FALLBACK_SHA=81489d12bdf717bd05e993419ba53a2e3a4e32df
PRE_PROD_SHA=ccaa757e49b83b4024d34c42ef4e5d07a3caa467
runuser -u khajiev13 -- git -C "$PROD_DIR" fetch origin \
  refs/heads/prod:refs/remotes/origin/prod \
  refs/heads/codex/production-webhook-startup-recovery-rollback:refs/remotes/origin/codex/production-webhook-startup-recovery-rollback
CANDIDATE_SHA="$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse origin/prod)"
ROLLBACK_COMMIT="$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse origin/codex/production-webhook-startup-recovery-rollback)"
test "$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse HEAD)" = "$FALLBACK_SHA"
test -z "$(runuser -u khajiev13 -- git -C "$PROD_DIR" status --porcelain)"
test "$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse "$ROLLBACK_COMMIT^{tree}")" = "$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse "$FALLBACK_SHA^{tree}")"
RELEASE_DIR="/root/.local/state/restaurant-mini-app/webhook-recovery-$CANDIDATE_SHA"
install -d -m 700 "$RELEASE_DIR"
RELEASE_STATE="$RELEASE_DIR/release.env"
```

- [ ] **Step 3: Record healthy identities and build the stopped fallback**

```bash
POSTGRES_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_postgres)"
FRONTEND_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_frontend)"
CADDY_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_caddy)"
CLOUDFLARED_CONTAINER_ID="$(docker inspect --format '{{.Id}}' restaurant_cloudflared)"
BITAGENT_CONTAINER_ID="$(docker inspect --format '{{.Id}}' lab4_professor_backend)"
BROKEN_BACKEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' restaurant_backend)"
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_postgres)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_frontend)" = healthy
test "$(docker inspect --format '{{.State.Health.Status}}' restaurant_caddy)" = healthy
test "$(docker inspect --format '{{.State.Running}}' restaurant_cloudflared)" = true
test "$(docker inspect --format '{{.State.Health.Status}}' lab4_professor_backend)" = healthy
FALLBACK_TAG="restaurant-mini-app-backend:rollback-${FALLBACK_SHA:0:12}-${CANDIDATE_SHA:0:12}"
docker build --pull=false --label "org.opencontainers.image.revision=$FALLBACK_SHA" --tag "$FALLBACK_TAG" "$PROD_DIR/backend"
FALLBACK_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$FALLBACK_TAG")"
test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$FALLBACK_TAG")" = "$FALLBACK_SHA"
test -z "$(docker ps -q --filter ancestor="$FALLBACK_IMAGE_ID")"
```

- [ ] **Step 4: Verify existing schema metadata**

Using only `information_schema.columns`, `pg_indexes`, and `pg_constraint`, require:

```text
22 expected release columns
9 release indexes
2 named release constraints
```

The 22 columns are `users.role` plus these `orders` columns:

```text
assigned_staff_id assigned_at delivered_at items_cost delivery_info table_id
table_title hall_id hall_title service_percent table_access_expires_at
alipos_sync_status alipos_sync_error cancel_requested_at client_request_id
refund_sync_status refund_sync_error alipos_status_check_attempted_at
alipos_status_checked_at invoice_cancel_status alipos_status_updated_at
```

The 9 indexes are:

```text
idx_orders_assigned_staff_id idx_orders_delivered_at idx_orders_staff_available
uq_orders_one_active_delivery_per_staff idx_orders_table_id
idx_orders_alipos_sync_status idx_orders_refund_sync_status
uq_orders_user_request idx_orders_inplace_workspace
```

The constraints are `ck_users_role_valid` and `orders_assigned_staff_id_fkey`. Run the metadata gate without selecting application rows:

```bash
COLUMN_COUNT="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) FROM information_schema.columns
WHERE (table_name = '\''users'\'' AND column_name = '\''role'\'')
   OR (table_name = '\''orders'\'' AND column_name IN (
     '\''assigned_staff_id'\'', '\''assigned_at'\'', '\''delivered_at'\'',
     '\''items_cost'\'', '\''delivery_info'\'', '\''table_id'\'', '\''table_title'\'',
     '\''hall_id'\'', '\''hall_title'\'', '\''service_percent'\'',
     '\''table_access_expires_at'\'', '\''alipos_sync_status'\'',
     '\''alipos_sync_error'\'', '\''cancel_requested_at'\'', '\''client_request_id'\'',
     '\''refund_sync_status'\'', '\''refund_sync_error'\'',
     '\''alipos_status_check_attempted_at'\'', '\''alipos_status_checked_at'\'',
     '\''invoice_cancel_status'\'', '\''alipos_status_updated_at'\''));"')"
INDEX_COUNT="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) FROM pg_indexes WHERE schemaname = '\''public'\'' AND indexname IN (
  '\''idx_orders_assigned_staff_id'\'', '\''idx_orders_delivered_at'\'',
  '\''idx_orders_staff_available'\'', '\''uq_orders_one_active_delivery_per_staff'\'',
  '\''idx_orders_table_id'\'', '\''idx_orders_alipos_sync_status'\'',
  '\''idx_orders_refund_sync_status'\'', '\''uq_orders_user_request'\'',
  '\''idx_orders_inplace_workspace'\'');"')"
CONSTRAINT_COUNT="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT count(*) FROM pg_constraint WHERE conname IN (
  '\''ck_users_role_valid'\'', '\''orders_assigned_staff_id_fkey'\'');"')"
```

If the values are not `22`, `9`, and `2`, apply only the four existing idempotent migrations in chronological order, then rerun these three commands:

```bash
for migration in \
  database/migrations/2026-07-07-staff-delivery-phase-1.sql \
  database/migrations/2026-07-13-qr-table-ordering.sql \
  database/migrations/2026-07-15-staff-table-inspection.sql \
  database/migrations/2026-07-18-release-safety.sql
do
  runuser -u khajiev13 -- git -C "$PROD_DIR" show "$CANDIDATE_SHA:$migration" \
    | docker exec -i restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
done
```

If metadata remains wrong, stop without building the candidate. Never query table rows.

Require the final values:

```bash
test "$COLUMN_COUNT" = 22
test "$INDEX_COUNT" = 9
test "$CONSTRAINT_COUNT" = 2
```

- [ ] **Step 5: Persist non-secret rollback state**

```bash
{
  printf 'PROD_DIR=%q\n' "$PROD_DIR"
  printf 'FALLBACK_SHA=%q\n' "$FALLBACK_SHA"
  printf 'PRE_PROD_SHA=%q\n' "$PRE_PROD_SHA"
  printf 'CANDIDATE_SHA=%q\n' "$CANDIDATE_SHA"
  printf 'ROLLBACK_COMMIT=%q\n' "$ROLLBACK_COMMIT"
  printf 'FALLBACK_TAG=%q\n' "$FALLBACK_TAG"
  printf 'FALLBACK_IMAGE_ID=%q\n' "$FALLBACK_IMAGE_ID"
  printf 'POSTGRES_CONTAINER_ID=%q\n' "$POSTGRES_CONTAINER_ID"
  printf 'FRONTEND_CONTAINER_ID=%q\n' "$FRONTEND_CONTAINER_ID"
  printf 'CADDY_CONTAINER_ID=%q\n' "$CADDY_CONTAINER_ID"
  printf 'CLOUDFLARED_CONTAINER_ID=%q\n' "$CLOUDFLARED_CONTAINER_ID"
  printf 'BITAGENT_CONTAINER_ID=%q\n' "$BITAGENT_CONTAINER_ID"
  printf 'BROKEN_BACKEND_IMAGE_ID=%q\n' "$BROKEN_BACKEND_IMAGE_ID"
} > "$RELEASE_STATE"
chmod 600 "$RELEASE_STATE"
```

- [ ] **Step 6: Checkout, build once, and recreate only the backend**

```bash
runuser -u khajiev13 -- git -C "$PROD_DIR" checkout --detach "$CANDIDATE_SHA"
test "$(runuser -u khajiev13 -- git -C "$PROD_DIR" rev-parse HEAD)" = "$CANDIDATE_SHA"
cd "$PROD_DIR"
docker build --label "org.opencontainers.image.revision=$CANDIDATE_SHA" --tag restaurant-mini-app-backend:latest "$PROD_DIR/backend"
CANDIDATE_IMAGE_ID="$(docker image inspect --format '{{.Id}}' restaurant-mini-app-backend:latest)"
test "$CANDIDATE_IMAGE_ID" != "$FALLBACK_IMAGE_ID"
test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' restaurant-mini-app-backend:latest)" = "$CANDIDATE_SHA"
docker image tag "$CANDIDATE_IMAGE_ID" "restaurant-mini-app-backend:candidate-${CANDIDATE_SHA:0:12}"
printf 'CANDIDATE_IMAGE_ID=%q\n' "$CANDIDATE_IMAGE_ID" >> "$RELEASE_STATE"
docker compose up -d --no-build --no-deps --force-recreate backend
for _ in $(seq 1 24); do
  BACKEND_HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' restaurant_backend)"
  test "$BACKEND_HEALTH" = healthy && break
  sleep 5
done
test "$BACKEND_HEALTH" = healthy
test "$(docker inspect --format '{{.Image}}' restaurant_backend)" = "$CANDIDATE_IMAGE_ID"
test "$(docker inspect --format '{{.RestartCount}}' restaurant_backend)" = 0
```

Do not run a second candidate build for the same SHA.

- [ ] **Step 7: Verify health, webhook, and role boundaries**

Require health without retaining response bodies:

```bash
test "$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/healthz)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/api/health)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 https://restaurant.labtutor.app/healthz)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 https://restaurant.labtutor.app/api/health)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 https://bitagent.labtutor.app/healthz)" = 200
```

Query Telegram under `set +x` and retain only safe fields:

```bash
set -a
source "$PROD_DIR/.env"
set +a
TELEGRAM_STATUS="$(curl -fsS --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
result = payload.get("result") or {}
print(
    "ok=%d url_ok=%d pending=%d error_free=%d"
    % (
        payload.get("ok") is True,
        result.get("url") == "https://restaurant.labtutor.app/api/webhooks/bot",
        int(result.get("pending_update_count", -1)),
        not result.get("last_error_message"),
    )
)
')"
unset TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET
test "$TELEGRAM_STATUS" = "ok=1 url_ok=1 pending=0 error_free=1"
```

Capture one existing ID per role without printing it, create short-lived JWTs inside the candidate container, discard bodies, and require the role boundaries:

```bash
CUSTOMER_ID="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT telegram_id FROM users WHERE role = '\''customer'\'' ORDER BY telegram_id LIMIT 1"')"
STAFF_ID="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT telegram_id FROM users WHERE role = '\''staff'\'' ORDER BY telegram_id LIMIT 1"')"
ADMIN_ID="$(docker exec restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT telegram_id FROM users WHERE role = '\''admin'\'' ORDER BY telegram_id LIMIT 1"')"
test -n "$CUSTOMER_ID"
test -n "$STAFF_ID"
test -n "$ADMIN_ID"
CUSTOMER_JWT="$(docker exec -e CONTROLLED_TELEGRAM_ID="$CUSTOMER_ID" restaurant_backend python -c 'import os; from app.middleware.telegram_auth import create_jwt; print(create_jwt(int(os.environ["CONTROLLED_TELEGRAM_ID"])))')"
STAFF_JWT="$(docker exec -e CONTROLLED_TELEGRAM_ID="$STAFF_ID" restaurant_backend python -c 'import os; from app.middleware.telegram_auth import create_jwt; print(create_jwt(int(os.environ["CONTROLLED_TELEGRAM_ID"])))')"
ADMIN_JWT="$(docker exec -e CONTROLLED_TELEGRAM_ID="$ADMIN_ID" restaurant_backend python -c 'import os; from app.middleware.telegram_auth import create_jwt; print(create_jwt(int(os.environ["CONTROLLED_TELEGRAM_ID"])))')"
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $CUSTOMER_JWT" http://127.0.0.1:8080/api/staff/tables)" = 403
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $STAFF_JWT" http://127.0.0.1:8080/api/staff/tables)" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $ADMIN_JWT" 'http://127.0.0.1:8080/api/admin/users?query=')" = 200
unset CUSTOMER_ID STAFF_ID ADMIN_ID CUSTOMER_JWT STAFF_JWT ADMIN_JWT
```

Never print IDs, JWTs, headers, or bodies.

- [ ] **Step 8: Resume supervision and observe one full cycle**

Record candidate backend container ID/restart count, exit WSL, then:

```bash
ssh restaurant 'schtasks.exe /Change /TN "\RestaurantWSLApps" /Enable'
ssh restaurant 'schtasks.exe /Run /TN "\RestaurantWSLApps"'
```

Poll until targeted supervisor count is one. For six minutes, poll every 15 seconds and require:

- candidate backend container/image IDs unchanged;
- backend health `healthy` and restart count unchanged;
- restaurant frontend/API and BitAgent public health succeed;
- recorded PostgreSQL/frontend/Caddy/tunnel/BitAgent container IDs unchanged.

Keep progress updates under 60 seconds apart.

- [ ] **Step 9: Run incident-only rollback if any gate fails**

Disable/end `\RestaurantWSLApps`, source `release.env`, verify fallback image ID/revision, and restore without building:

```bash
docker image tag "$FALLBACK_IMAGE_ID" restaurant-mini-app-backend:latest
runuser -u khajiev13 -- git -C "$PROD_DIR" checkout --detach "$ROLLBACK_COMMIT"
cd "$PROD_DIR"
docker compose up -d --no-build --no-deps --force-recreate backend
```

Require fallback backend/public API health, then fast-forward remote `prod` without force:

```bash
git fetch origin prod
test "$(git rev-parse origin/prod)" = "$CANDIDATE_SHA"
git push origin "$ROLLBACK_COMMIT:refs/heads/prod"
```

Re-enable supervision only after fallback health. Verify checkout tree `81489d1`, immutable fallback image, and unchanged non-backend IDs. Do not claim the current release succeeded after rollback.

- [ ] **Step 10: Report successful acceptance**

Report only candidate SHA, candidate backend image ID, health outcomes, role-boundary status codes, final restart count, six-minute stability duration, and confirmation that numeric QR work, secrets, volumes, frontend, Caddy, tunnel, and BitAgent were untouched.
