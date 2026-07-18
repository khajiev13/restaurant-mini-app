# Table Online Payment Global Enablement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Enable the existing online-payment capability for every authenticated table-order customer while preserving dynamic AliPOS hall percentages and the subtotal/payable-total split.

**Architecture:** The application code is already complete on codex/alipos-inplace-total-fix at 81489d12bdf717bd05e993419ba53a2e3a4e32df. This rollout verifies that exact code, checks production for unresolved financial state, sets the existing backend flag to true, recreates only the backend container, and verifies the runtime capability and current AliPOS hall percentages without exposing secrets or customer data.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic Settings, PostgreSQL, pytest, React, TypeScript, Vitest, Docker Compose, WSL2, SSH.

## Global Constraints

- service_percent comes from the selected table's current AliPOS hall returned by GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables; it is not hard-coded or accepted from the browser.
- Multicard invoices, callback verification, receipts, cancellations, and refunds use the backend-calculated service-inclusive total_amount.
- AliPOS in-place paymentInfo.itemsCost and paymentInfo.total use items_cost.
- AliPOS delivery totals and delivery online payment behavior remain unchanged.
- Keep the backend capability gate and tester allowlist code; global availability is controlled by INPLACE_ONLINE_PAYMENT_ENABLED=true.
- Do not print .env, credentials, tokens, customer data, provider payloads, payment UUIDs, table UUIDs, or raw AliPOS responses.
- Do not restart PostgreSQL, frontend, Caddy, or Cloudflared for the environment-only change.
- Do not enable while unresolved table invoices, refunds, or paid AliPOS synchronization outcomes exist.
- Roll back immediately by restoring INPLACE_ONLINE_PAYMENT_ENABLED=false and recreating only the backend if a verification gate fails.

---

### Task 1: Verify the exact application candidate

**Files:**
- Verify: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/app/services/table_access_service.py
- Verify: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/app/services/order_service.py
- Verify: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/app/routers/webhooks.py
- Verify: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/frontend/src/pages/artisan/ArtisanCheckoutPage.tsx
- Test: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/tests/test_order_service.py
- Test: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/tests/api/test_users.py
- Test: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend/tests/api/test_webhooks.py
- Test: /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx

**Interfaces:**
- Consumes: existing branch tip 81489d12bdf717bd05e993419ba53a2e3a4e32df and its installed backend/frontend dependencies.
- Produces: current test evidence for dynamic servicePercent, Multicard payable totals, AliPOS in-place subtotals, callback validation, and global capability rendering.

- [ ] **Step 1: Confirm the candidate worktree is exact and clean**

Run:

~~~bash
git -C /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix status --short --branch
git -C /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix rev-parse HEAD
~~~

Expected: the branch is codex/alipos-inplace-total-fix, there are no changed files, and HEAD is 81489d12bdf717bd05e993419ba53a2e3a4e32df.

- [ ] **Step 2: Run focused backend financial-contract tests**

Run:

~~~bash
cd /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend
.venv/bin/pytest tests/test_order_service.py tests/api/test_users.py tests/api/test_webhooks.py -q
~~~

Expected: all selected tests pass. The assertions prove an in-place order persists the service-inclusive payable total, sends the subtotal to AliPOS, creates a Multicard invoice for the payable total, and validates callbacks against that same payable total.

- [ ] **Step 3: Run focused frontend capability tests**

Run:

~~~bash
cd /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/frontend
npm test -- ArtisanCheckoutPage.test.tsx stores/__tests__/authStore.test.ts
npm run typecheck
npm run build
~~~

Expected: Vitest passes, TypeScript exits zero, and the production build succeeds. Table checkout shows Online only from the backend capability; delivery continues to show both payment methods.

- [ ] **Step 4: Run whole-branch verification**

Run:

~~~bash
cd /Users/khajievroma/Projects/restaurant-mini-app-worktrees/alipos-inplace-total-fix/backend
.venv/bin/ruff check .
.venv/bin/pytest -q
cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
cd ..
docker compose config --quiet
git diff --check
~~~

Expected: every command exits zero and the worktree remains clean.

---

### Task 2: Run the secret-safe production preflight

**Files:**
- Verify remotely: /home/khajiev13/apps/restaurant-mini-app/.env
- Verify remotely: /home/khajiev13/apps/restaurant-mini-app/backend/app/services/order_service.py
- Verify remotely: the production orders table through aggregate counts only.

**Interfaces:**
- Consumes: the verified exact candidate and SSH alias restaurant.
- Produces: a go/no-go decision with application SHA, health, runtime flag state, and three zero financial-risk counts.

- [ ] **Step 1: Confirm production code contains the required fixes**

Run:

~~~bash
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- bash -lc '\''cd /home/khajiev13/apps/restaurant-mini-app && git status --short && git rev-parse HEAD && git merge-base --is-ancestor 46477b5 HEAD && git merge-base --is-ancestor d99f741 HEAD && git merge-base --is-ancestor b7c5738 HEAD && echo table_online_code=ready'\'''
~~~

Expected: the production checkout is clean, prints its SHA, and ends with table_online_code=ready. Any non-zero exit stops the rollout.

- [ ] **Step 2: Confirm the stack and public routes are healthy**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc '\''cd /home/khajiev13/apps/restaurant-mini-app && docker compose ps && curl -fsS http://127.0.0.1:8080/healthz >/dev/null && curl -fsS http://127.0.0.1:8080/api/health >/dev/null && curl -fsS https://restaurant.labtutor.app/healthz >/dev/null && curl -fsS https://restaurant.labtutor.app/api/health >/dev/null && echo health=ready'\'''
~~~

Expected: application containers are running/healthy and output ends with health=ready.

- [ ] **Step 3: Read only the rollout capability state**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker exec restaurant_backend python -c '\''from app.config import settings; print("enabled=" + str(settings.inplace_online_payment_enabled).lower()); print("tester_count=" + str(len(settings.inplace_online_payment_test_ids)))'\'''
~~~

Expected before rollout: enabled=false. Only the tester count is printed; tester IDs and all other environment values remain private.

- [ ] **Step 4: Prove there is no unresolved table-payment state**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker exec restaurant_postgres sh -lc '\''psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FILTER (WHERE payment_status IN ('\''pending'\'','\''invoice_unknown'\'')) AS unresolved_invoices, count(*) FILTER (WHERE payment_status IN ('\''refund_pending'\'','\''refund_failed'\'') OR refund_sync_status IN ('\''queued'\'','\''sending'\'','\''unknown'\'','\''failed'\'')) AS unresolved_refunds, count(*) FILTER (WHERE payment_status='\''paid'\'' AND alipos_sync_status IN ('\''sending'\'','\''unknown'\'','\''failed'\'')) AS unresolved_paid_alipos FROM orders WHERE discriminator='\''inplace'\'' AND payment_method='\''rahmat'\'';"'\'''
~~~

Expected: 0|0|0. Any non-zero field stops the rollout without modifying production.

- [ ] **Step 5: Confirm AliPOS currently returns hall percentages without dumping tenant data**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker exec restaurant_backend python -c '\''import asyncio; from app.services.alipos_api import get_halls_and_tables; payload=asyncio.run(get_halls_and_tables()); values=sorted({str(hall.get("servicePercent") or 0) for hall in payload.get("halls", [])}); print("hall_count=" + str(len(payload.get("halls", [])))); print("service_percents=" + ",".join(values))'\'''
~~~

Expected: a positive hall count and one or more percentages. No hall/table IDs, titles, credentials, or raw response are printed.

---

### Task 3: Enable globally, verify, and preserve rollback

**Files:**
- Modify remotely: /home/khajiev13/apps/restaurant-mini-app/.env
- Create remotely: timestamped .env.before-table-online-<timestamp>.bak beside the production environment file.

**Interfaces:**
- Consumes: Task 2's all-green preflight.
- Produces: INPLACE_ONLINE_PAYMENT_ENABLED=true loaded by the production backend, with all health and capability checks green.

- [ ] **Step 1: Back up the environment file and change only the global flag**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc '\''set -euo pipefail
app=/home/khajiev13/apps/restaurant-mini-app
stamp=$(date +%Y%m%d-%H%M%S)
cp "$app/.env" "$app/.env.before-table-online-$stamp.bak"
if grep -q "^INPLACE_ONLINE_PAYMENT_ENABLED=" "$app/.env"; then
  sed -i "s/^INPLACE_ONLINE_PAYMENT_ENABLED=.*/INPLACE_ONLINE_PAYMENT_ENABLED=true/" "$app/.env"
else
  printf "\nINPLACE_ONLINE_PAYMENT_ENABLED=true\n" >> "$app/.env"
fi
grep -q "^INPLACE_ONLINE_PAYMENT_ENABLED=true$" "$app/.env"
echo env_flag=updated'\'''
~~~

Expected: env_flag=updated. The backup filename is not used to display any environment contents.

- [ ] **Step 2: Recreate only the backend service**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc '\''cd /home/khajiev13/apps/restaurant-mini-app && docker compose up -d --no-deps --force-recreate backend && docker compose ps backend'\'''
~~~

Expected: restaurant_backend is running and becomes healthy. PostgreSQL, frontend, Caddy, and Cloudflared are not recreated.

- [ ] **Step 3: Verify the loaded capability and public health**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc '\''set -euo pipefail
for attempt in 1 2 3 4 5 6; do
  if docker exec restaurant_backend python -c "import urllib.request; urllib.request.urlopen('\''http://127.0.0.1:8000/health'\'', timeout=3).read()"; then break; fi
  sleep 5
done
docker exec restaurant_backend python -c "from app.config import settings; assert settings.inplace_online_payment_enabled is True; print('\''enabled=true'\'')"
curl -fsS http://127.0.0.1:8080/healthz >/dev/null
curl -fsS http://127.0.0.1:8080/api/health >/dev/null
curl -fsS https://restaurant.labtutor.app/healthz >/dev/null
curl -fsS https://restaurant.labtutor.app/api/health >/dev/null
echo health=ready'\'''
~~~

Expected: enabled=true and health=ready.

- [ ] **Step 4: Verify no secret-bearing or financial errors appeared during restart**

Run:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker logs --since 10m restaurant_backend --tail 200'
~~~

Expected: normal startup and health traffic, with no traceback, payment/refund failure, raw provider body, credential, or token. Stop and roll back if a financial or startup error appears.

- [ ] **Step 5: Roll back immediately if any post-enable gate fails**

Run only on a failed post-enable check:

~~~bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc '\''set -euo pipefail
app=/home/khajiev13/apps/restaurant-mini-app
sed -i "s/^INPLACE_ONLINE_PAYMENT_ENABLED=.*/INPLACE_ONLINE_PAYMENT_ENABLED=false/" "$app/.env"
cd "$app"
docker compose up -d --no-deps --force-recreate backend
docker exec restaurant_backend python -c "from app.config import settings; assert settings.inplace_online_payment_enabled is False; print('\''enabled=false'\'')"'\'''
~~~

Expected: enabled=false; delivery online payment remains available.

- [ ] **Step 6: Customer-visible verification**

Refresh the Telegram Mini App authentication/profile and open checkout from a table QR. Confirm both Cash and Online are visible. The displayed service percentage must match the current AliPOS hall value from Task 2, and changing payment method must not change the displayed total.

Expected: a table with a 4,000 UZS subtotal and a live AliPOS percentage of 10 shows 400 UZS service and a 4,400 UZS payable total. Any other live percentage produces its corresponding backend-calculated service charge rather than 10%.

- [ ] **Step 7: Financial smoke test handoff**

Ask the user to place one inexpensive online table order. After their payment, verify only safe structured order diagnostics and aggregate/provider/POS views: Multicard charged the persisted total_amount, the callback marked that amount paid, AliPOS received items_cost, and the AliPOS Desktop bill applies the dynamic hall service exactly once with no remaining balance.

Expected: all amounts reconcile. If they do not, execute Step 5 immediately and resolve the already-created invoice/order through the existing safe cancellation or refund flow.

