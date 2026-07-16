# Table Inspection Release Safety Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Every behavior change begins with a failing test, and every task receives specification and code-quality review before the next task starts.

**Goal:** Close the whole-release safety findings that block deployment of the staff/admin table inspection workspace, without expanding the accepted inspection-first product scope.

**Architecture:** Keep each external provider mutation as a three-phase operation: durably claim the local row, perform exactly one provider mutation outside a database transaction, then conditionally finalize only if the row is still in a compatible nonterminal state. Treat any possibly accepted provider outcome as unknown, reconcile it only with provider reads, and make terminal states absorbing. Reuse existing cart-conflict, staff-order, webhook, and rollout mechanisms for the UI and operational fixes.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL 16, httpx, pytest, React 19, TypeScript 5.7, Zustand 5, Axios, Vitest, Testing Library, Bash runbook commands.

## Global constraints

- Do not change the approved table-inspection scope: all AliPOS directory tables, active mini-app `inplace` orders only, combined summaries, active-order detail, and browse-only menu reuse.
- Do not infer AliPOS occupancy, reservations, or a global POS bill.
- Never automatically repeat an AliPOS create/cancel mutation, Multicard invoice create, or Multicard refund after an ambiguous result.
- Provider POST/DELETE calls occur only after a durable local attempt marker is committed.
- Provider calls occur outside long-lived row-lock transactions.
- Finalizers use current database state or conditional `UPDATE` predicates; stale ORM instances cannot overwrite webhook/reconciler results.
- `refunded` and other terminal provider-confirmed states never move backward.
- Do not log provider response bodies, credentials, checkout URLs, invoice/payment UUIDs, or exception chains containing provider URLs.
- Preserve exact `client_request_id` idempotency: one key represents one local order and never turns a prior definite failure into HTTP success.
- A price change requires a refreshed cart and a second explicit customer submit before any order, invoice, or provider mutation.
- Staff take-order mutation timeout must be longer than the backend provider deadline; ambiguous client outcomes are reconciled by GET and never by automatic POST retry.
- Do not rotate production secrets as part of this release. Make startup registration correct for the unchanged configured secret and record dual-secret overlap as an unsupported future requirement, not a current procedure.
- Use the existing local PostgreSQL service for migration/application tests. Run the destructive final-admin proof once in a fresh volume-free PostgreSQL container with a uniquely named database; do not repeatedly rebuild Docker images.

---

### Task 1: Make AliPOS create outcomes semantic and stale-safe

**Files:**
- Modify: `backend/app/services/alipos_api.py`
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/tests/test_order_service.py`
- Modify: `backend/tests/api/test_webhooks.py`

**Contract:**
- `AliPOSRejected` is limited to the explicit proven order-POST allowlist `{400, 401, 403, 404, 405, 422}`. Every other post-send response defaults to unknown.
- `AliPOSUnknownOutcome` covers transport failures, HTTP 408/409/425/429, all 5xx, and malformed/missing success identifiers.
- A possibly accepted response produces `SYNC_UNKNOWN`, keeps a paid payment paid, queues no refund, and is never retried.
- Create success persists the provider ID/sync result but preserves a faster webhook status and order number.

- [ ] **Step 1: Add RED provider-classification tests**

Add `backend/tests/test_order_service.py::test_alipos_create_order_ambiguous_http_status_is_unknown`, parametrized with `408, 409, 418, 425, 429, 500, 502, 503, 504`. Assert one POST and `AliPOSUnknownOutcome`, not `AliPOSRejected`. Add a separate rejection test parametrized with the exact allowlist `{400, 401, 403, 404, 405, 422}` so no range-based implementation can pass accidentally.

Add `backend/tests/test_order_service.py::test_paid_alipos_ambiguous_http_response_does_not_refund`. Drive a real mocked HTTP 502 through `alipos_api.create_order`; assert `status=SYNC_UNKNOWN`, `alipos_sync_status=unknown`, `payment_status=paid`, no refund call, and no second POST.

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_order_service.py::test_alipos_create_order_ambiguous_http_status_is_unknown \
  tests/test_order_service.py::test_paid_alipos_ambiguous_http_response_does_not_refund -q
```

Expected: RED because 408/429/5xx currently become definite rejection/refund.

- [ ] **Step 2: Add RED webhook-race test**

Add `backend/tests/api/test_webhooks.py::test_paid_submit_success_preserves_status_webhook_that_wins_race`. Block `create_order` after the durable `sending` commit, send an authenticated `ACCEPTED_BY_RESTAURANT` webhook by persisted `eatsId`, release a valid `orderId`, and assert `synced` plus provider ID while status/order number remain webhook-derived.

Add `backend/tests/api/test_webhooks.py::test_paid_submit_unknown_preserves_status_webhook_that_wins_race`. Win the same race with a mocked HTTP 502/transport ambiguity; assert sync outcome `unknown` and no refund/retry while webhook status/order number remain unchanged.

Run the single test and confirm it fails with final status `NEW`.

- [ ] **Step 3: Implement semantic classification and conditional success finalization**

In `alipos_api.create_order`, classify only `{400, 401, 403, 404, 405, 422}` as `AliPOSRejected`. Convert every other post-send HTTP/transport result, including unlisted 4xx, to `AliPOSUnknownOutcome`. Validate the response is an object with a UUID-compatible `orderId`; otherwise raise `AliPOSUnknownOutcome` from no unsafe provider exception.

In `submit_order_to_alipos`, use a current-row conditional finalizer after provider I/O. Always persist `alipos_order_id`, `alipos_sync_status=synced`, and clear the sync error when the row is still the claimed attempt. Set `status=NEW` only while the current database status is `NEW` or `PAID_AWAITING_RESTAURANT`; preserve later webhook statuses and `order_number`. Apply the same current-row discipline to failure/unknown finalization.

- [ ] **Step 4: Run focused and adjacent tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_order_service.py \
  tests/api/test_webhooks.py \
  tests/api/test_orders_status.py -q
cd backend && .venv/bin/ruff check app/services/alipos_api.py app/services/order_service.py tests/test_order_service.py tests/api/test_webhooks.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/alipos_api.py backend/app/services/order_service.py backend/tests/test_order_service.py backend/tests/api/test_webhooks.py
git commit -m "fix: preserve ambiguous AliPOS order outcomes"
```

---

### Task 2: Make cancellation and refunds crash-safe and eventually reconciled

**Files:**
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/services/multicard_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py` only if a bounded reconciliation interval setting is needed
- Modify: `backend/tests/test_order_service.py`
- Modify: `backend/tests/api/test_orders_status.py`
- Modify: `backend/tests/api/test_webhooks.py` if callback/refund terminal guards need cross-component coverage

**Contract:**
- AliPOS cancel follows `not_started -> sending -> cancelled|unknown`; `sending` is committed before DELETE.
- `sending/unknown` cancellation is reconciled only with GET and never issues another DELETE.
- GET-confirmed `CANCELLED` records cancellation and queues exactly one paid refund atomically.
- GET-confirmed accepted/later states move cancellation to absorbing `not_cancelled`, update the restaurant status, queue no refund, issue no DELETE, and leave periodic scans.
- Refund DELETE claim remains single-attempt; dispatch and GET reconciliation finalize conditionally and cannot downgrade `refunded`.
- Runtime reconciliation runs periodically, not only at startup.
- Refund logs expose only local order ID and a bounded outcome category.

- [ ] **Step 1: Add RED cancellation tests**

Add to `backend/tests/api/test_orders_status.py`:

- `test_alipos_cancel_attempt_is_durable_before_delete`
- `test_unknown_alipos_cancel_retry_never_sends_second_delete`
- `test_unknown_paid_cancel_reconciles_cancelled_and_queues_one_refund`
- `test_interrupted_cancel_recovery_uses_get_without_delete`
- `test_unknown_cancel_reconciles_later_status_to_not_cancelled_without_refund`

The first inspects the row from a second session inside the mocked DELETE and requires committed `sending` plus `cancel_requested_at`. The second performs two customer DELETE requests after one timeout and requires one provider DELETE total. The third seeds `unknown`, returns provider `CANCELLED`, and requires one queued/dispatched refund. The fourth seeds `sending` as after a process crash and proves GET-only recovery. The fifth returns `ACCEPTED_BY_RESTAURANT` (and one later status), requires `not_cancelled`, no refund/DELETE, and proves a second reconciliation scan does not select the row.

Run the four tests and confirm RED.

- [ ] **Step 2: Add RED terminal-safety, liveness, and log tests**

Add to `backend/tests/test_order_service.py`:

- `test_refund_terminal_state_cannot_be_downgraded_by_stale_dispatch_writer`
- `test_refund_terminal_state_cannot_be_downgraded_by_stale_reconciler`
- `test_runtime_unknown_refund_is_reconciled_without_restart`
- `test_refund_error_log_excludes_payment_uuid_and_provider_url`
- `test_provider_reconciliation_loop_runs_after_startup_survives_tick_error_and_stops_on_shutdown`

Use two sessions to commit `refunded/refunded` while another dispatch/reconciler holds stale state. Capture a canary payment UUID and assert logs exclude the canary, `/payment/`, raw response details, and credentials. The lifecycle test must start the FastAPI app/task wiring rather than call only the one-shot helper: prove a runtime-created unknown refund and cancellation are processed, one tick exception is logged safely and the next tick still runs, and shutdown cancels/awaits the task with no orphan.

- [ ] **Step 3: Implement claim/I/O/conditional-finalize cancellation**

Split first cancellation into: read current AliPOS status; reacquire/lock and revalidate the local row; commit `alipos_cancel_status=sending` and timestamp; perform one DELETE; conditionally finalize. If a row is already `sending/unknown`, run only GET reconciliation. A shared cancellation finalizer must set local `CANCELLED` and queue a paid refund in one transaction, guarded by `payment_status=paid` and no existing refund state. Dispatch the queued refund after that commit.

Add startup/periodic reconciliation for stranded `sending/unknown` cancellations; provider `NEW` remains unknown without DELETE, provider `CANCELLED` finalizes, and later accepted/terminal statuses update local status plus absorbing cancellation state `not_cancelled` without refund.

- [ ] **Step 4: Implement refund conditional finalizers and periodic tick**

Preserve the existing row-lock claim for `queued -> sending`. After DELETE, finalize with an expected-state `UPDATE`; success may move `sending/unknown -> refunded`, while failed/unknown outcomes may update only compatible nonterminal rows. Refactor GET reconciliation into bounded per-order reads outside row-lock transactions followed by conditional updates. Add a one-shot runtime reconciler and a supervised periodic startup task, following the existing payment-expiry lifecycle and using an advisory lock or safe duplicate GETs.

Replace `logger.exception` in refund paths with structured `warning/error` calls that do not include exception text or traceback. In `multicard_api.py`, suppress unsafe chained causes after safe status/category extraction so no caller can accidentally render a URL containing the payment UUID.

- [ ] **Step 5: Run focused and adjacent tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_order_service.py \
  tests/api/test_orders_status.py \
  tests/api/test_webhooks.py \
  tests/test_staff_table_service.py \
  tests/api/test_staff_tables.py -q
cd backend && .venv/bin/ruff check app/services/order_service.py app/services/multicard_api.py app/main.py tests/test_order_service.py tests/api/test_orders_status.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/order_service.py backend/app/services/multicard_api.py backend/app/main.py backend/app/config.py backend/tests/test_order_service.py backend/tests/api/test_orders_status.py backend/tests/api/test_webhooks.py
git commit -m "fix: reconcile cancellation and refund outcomes"
```

---

### Task 3: Make Multicard invoice creation conservative and callback-compatible

**Files:**
- Modify: `backend/app/services/multicard_api.py`
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/routers/webhooks.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `backend/tests/test_multicard_api.py` or the existing Multicard service test file
- Modify: `backend/tests/test_order_service.py`
- Modify: `backend/tests/api/test_webhooks.py`
- Modify: `backend/tests/test_config.py`

**Contract:**
- A newly persisted online order starts in durable `invoice_queued`; only that never-attempted state may be claimed for POST.
- Invoice attempt is durably `invoice_sending` before POST.
- Token/prerequisite failure before POST and explicit deterministic rejection may become `failed`.
- Transport errors, HTTP 408/409/425/429, all 5xx, malformed 2xx, missing required success data, or interrupted `invoice_sending` become `invoice_unknown/PAYMENT_REVIEW`.
- Definite rejection is limited to the documented pairs `HTTP 400 + ERROR_FIELDS` and `HTTP 404 + ERROR_NOT_FOUND`; every unlisted/malformed status-code pair is unknown.
- If an incomplete response contains a provider UUID, persist it in the unknown state and reconcile only with `GET /payment/invoice/{uuid}`; never repeat POST.
- Startup retries only `invoice_queued`; it converts interrupted `invoice_sending` to unknown without POST.
- Unknown/sending invoices cannot be retried or switched to cash; an authentic matching callback remains authoritative.
- Callback winning the race cannot be overwritten by the invoice response finalizer.
- Legacy delivery rows that already have an AliPOS order are marked paid/synced without a second AliPOS create.

- [ ] **Step 1: Add RED invoice outcome tests**

Add tests for:

- real HTTP 503 -> `InvoiceOutcomeUnknown`
- malformed/missing-data 2xx -> `InvoiceOutcomeUnknown`, preserving any returned UUID
- exact documented `HTTP 400 + ERROR_FIELDS` and `HTTP 404 + ERROR_NOT_FOUND` -> `InvoiceRejected`
- unlisted 4xx/error-code combinations, including documented ambiguity codes, -> `InvoiceOutcomeUnknown`
- `backend/tests/test_order_service.py::test_invoice_ambiguous_outcome_blocks_retry_and_cash_switch`
- `backend/tests/test_order_service.py::test_invoice_recovery_retries_only_never_attempted_rows`
- `backend/tests/test_order_service.py::test_malformed_invoice_success_with_uuid_preserves_reference_and_reconciles_by_get`
- `backend/tests/api/test_webhooks.py::test_callback_wins_invoice_create_finalizer_race`

For the partial-UUID case, make the first POST return incomplete success data containing a UUID, then have one GET return a complete usable invoice. Assert the UUID is committed before/through reconciliation, the checkout moves to pending without another POST, and GET failure/nonfinal data remains unknown. Assert no automatic second POST, no cancellation/switch, and callback acceptance from `invoice_sending` and `invoice_unknown`.

- [ ] **Step 2: Implement typed invoice boundary and conditional finalizer**

Add sanitized `InvoicePreSubmitError`, `InvoiceRejected`, and `InvoiceOutcomeUnknown(invoice_uuid=None)` exceptions. Only `HTTP 400 + ERROR_FIELDS` and `HTTP 404 + ERROR_NOT_FOUND` are definite; all other post-send combinations are unknown. Validate a successful response object, provider UUID, and checkout target; a UUID-less legacy checkout is permitted only behind `MULTICARD_ALLOW_UUIDLESS_SANDBOX_CHECKOUT=false`, with config parsing tests and `.env.example` default false. Persist new online rows as `invoice_queued`, atomically claim only that state into `invoice_sending`, and commit `status=PAYMENT_REVIEW` plus cleared provider fields before POST. Finalize with a conditional update only while still `invoice_sending`; callback-paid rows remain paid. On incomplete data, carry and persist any UUID from the exception. Startup recovery schedules only `invoice_queued` rows and changes stranded `invoice_sending` to `invoice_unknown/PAYMENT_REVIEW` without POST.

Add a bounded invoice-unknown reconciler for rows with a provider UUID. It calls only `GET /payment/invoice/{uuid}` outside the row transaction, conditionally persists a complete usable invoice as `pending/AWAITING_PAYMENT`, and otherwise leaves the row unknown. Wire it into the tested runtime provider-reconciliation lifecycle from Task 2. It must never call invoice POST.

Allow callback state validation for `invoice_queued`, `invoice_sending`, `pending`, and `invoice_unknown`; continue rejecting failed/expired/cancelled or mismatched payments.

- [ ] **Step 3: Add RED legacy cutover callback test and implement narrow branch**

Add `backend/tests/api/test_webhooks.py::test_legacy_pending_delivery_callback_marks_paid_without_second_alipos_create`. Seed the exact legacy shape: `discriminator=delivery`, `payment_method=rahmat`, `payment_provider=multicard`, `payment_status=pending`, non-null AliPOS/invoice IDs, and `alipos_sync_status` null or `synced`; parameterize `status=NEW` and one advanced restaurant status. Submit a valid callback and assert HTTP 200, paid fields, `alipos_sync_status=synced`, preserved restaurant status/ID, and zero dispatch/create calls.

Implement only this narrow compatibility branch. Normal candidate rows continue to queue one AliPOS submission after payment.

- [ ] **Step 4: Run focused and adjacent tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_multicard_api.py \
  tests/test_order_service.py \
  tests/api/test_webhooks.py \
  tests/api/test_orders_status.py -q
cd backend && .venv/bin/ruff check app/services/multicard_api.py app/services/order_service.py app/routers/webhooks.py app/main.py app/config.py tests/test_config.py
```

If the Multicard tests live under a different existing filename, use `rg --files backend/tests | rg 'multicard|payment'` and run that exact file; do not create a duplicate test module.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/multicard_api.py backend/app/services/order_service.py backend/app/routers/webhooks.py backend/app/main.py backend/app/config.py .env.example backend/tests
git commit -m "fix: preserve uncertain Multicard invoice outcomes"
```

---

### Task 4: Preserve definite cash failure across idempotent replays

**Files:**
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/tests/api/test_orders_create.py`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx` only if current behavior is not already covered

**Contract:** A repeated `client_request_id` for an AliPOS definite failure returns the same semantic 502 without a provider mutation, through both the early lookup and IntegrityError winner paths. A concurrent replay that observes `sending` returns an explicit non-success/in-progress response and never 201. Neither case causes the frontend to navigate or clear the cart.

- [ ] **Step 1: Add RED API replay test**

Add `test_same_client_request_id_replays_cash_submission_failure_without_provider_retry`. Make the first AliPOS create deterministically reject, submit the same body twice, and assert both responses are 502, one row, one provider POST, stored `failed/SUBMISSION_FAILED`, and no refund.

Add `test_client_request_id_integrity_race_winner_replays_failed_result` by forcing the insert loser through the IntegrityError winner lookup; assert the same 502 and no second provider call. Add `test_client_request_id_replay_while_submission_sending_is_not_reported_as_created`; block the first provider call after the durable claim, replay the key, and require an explicit 409/in-progress contract with one provider POST total and no nominal order-success response.

- [ ] **Step 2: Implement failed-replay branch**

Centralize one replay classifier and call it from both the early duplicate lookup and IntegrityError winner branch. Preserve existing handling for queued/synced/unknown and online states. When `alipos_sync_status=failed`, re-raise `OrderSubmissionRejected` with the bounded stored failure category; do not mutate or call the provider. When state is `sending`, raise a dedicated in-progress conflict mapped to an allowlisted 409 payload containing only the local order ID/status; do not return 201 or call the provider.

- [ ] **Step 3: Prove frontend retention**

Keep/add a checkout test so a 502 leaves cart contents, route, and `client_request_id` unchanged and displays the generic safe error. Add `rejects_a_nominal_success_body_for_submission_failed_order`: resolve a nominal 201 body containing `status=SUBMISSION_FAILED` and `alipos_sync_status=failed`, then assert the frontend defense still leaves the cart/route unchanged and shows an error. Do not automatically generate a new provider mutation.

- [ ] **Step 4: Run and commit**

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_orders_create.py tests/test_order_service.py -q
cd frontend && npm test -- --run src/pages/artisan/ArtisanCheckoutPage.test.tsx
git add backend/app/services/order_service.py backend/tests/api/test_orders_create.py frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx
git commit -m "fix: replay failed cash orders consistently"
```

---

### Task 5: Require explicit customer consent after price changes

**Files:**
- Modify: `backend/app/services/menu_catalog_service.py`
- Modify: `backend/tests/test_menu_catalog_service.py`
- Modify: `backend/tests/api/test_orders_create.py`
- Modify: `frontend/src/stores/cartStore.ts`
- Modify: `frontend/src/stores/__tests__/cartStore.test.ts`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx`

**Contract:** A stale item or modifier price raises the existing allowlisted `cart_conflict` before any local/provider/payment side effect. Menu refresh updates price-only cart changes, and checkout requires a second explicit click with a new request ID.

- [ ] **Step 1: Add RED backend tests**

Replace the stale-price acceptance characterization with `test_price_cart_rejects_stale_item_price` and add `test_price_cart_rejects_stale_modifier_price`. Require `CartConflict` changes containing only relevant item/modifier IDs and reason `price_changed`.

Add `backend/tests/api/test_orders_create.py::test_repriced_cart_has_no_order_or_provider_side_effects`, parametrized for `cash` and `rahmat`. In both cases assert 409 and no `Order`; for cash assert no AliPOS create, and for Rahmat assert no Multicard invoice (while also asserting the other provider mutation remains absent where applicable).

- [ ] **Step 2: Implement price comparison**

Normalize submitted and current prices to `Decimal` and compare before building the priced cart. Keep the server authoritative for totals; use the submitted price only as evidence of what the customer saw. On any mismatch append allowlisted `price_changed` and raise before persistence.

- [ ] **Step 3: Add RED frontend tests and implement price-only reconciliation**

Add `updates_price_only_catalog_changes` in the Zustand store tests. Extend the reconciliation result with `repriced` or `catalogChanged`; persist merged current catalog data whenever any relevant field changes, even without removal/reduction.

Add `requires_a_second_click_after_server_price_conflict`: first POST returns 409, refresh supplies a higher price, cart/total update, route/cart stay, only one POST occurs; second explicit click sends current price and a new `client_request_id`.

- [ ] **Step 4: Run and commit**

```bash
cd backend && .venv/bin/python -m pytest tests/test_menu_catalog_service.py tests/api/test_orders_create.py -q
cd frontend && npm test -- --run src/stores/__tests__/cartStore.test.ts src/pages/artisan/ArtisanCheckoutPage.test.tsx
cd frontend && npm run typecheck
git add backend/app/services/menu_catalog_service.py backend/tests/test_menu_catalog_service.py backend/tests/api/test_orders_create.py frontend/src/stores/cartStore.ts frontend/src/stores/__tests__/cartStore.test.ts frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx
git commit -m "fix: require confirmation after menu repricing"
```

---

### Task 6: Bound and reconcile staff take-order outcomes

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/staff_delivery_service.py`
- Modify: `backend/tests/api/test_staff_delivery.py`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/staffApi.ts`
- Create or modify: `frontend/src/services/staffApi.test.ts`
- Modify: `frontend/src/pages/staff/StaffOrdersPage.tsx`
- Modify: `frontend/src/pages/staff/StaffOrderDetailPage.tsx`
- Modify: corresponding staff page tests

**Contract:** The provider status read has an end-to-end backend deadline shorter than the explicit client mutation timeout. It runs outside the row lock. Same-staff replay is idempotent. A client timeout is reconciled by bounded active-order GETs; POST is never automatically repeated.

- [ ] **Step 1: Add RED backend deadline/idempotency tests**

Add:

- `test_take_order_provider_deadline_expires_without_assignment`
- `test_take_order_provider_read_happens_without_row_lock`
- `test_take_order_replay_by_same_staff_returns_active_order`
- `test_take_order_preserves_webhook_status_that_advances_between_provider_read_and_lock`
- `test_take_order_operation_deadline_cancels_contended_lock_without_late_assignment`

Use tiny patched provider and whole-operation deadlines and a never-completing provider read. Assert bounded 503, explicit rollback, no assignment/late commit, and safe row availability. Use a second session to prove the provider await is not holding `FOR UPDATE`. For same-staff replay, assert success occurs before provider I/O and the provider mock is untouched. For the stale-read race, let GET observe `TAKEN_BY_COURIER`, commit a webhook advance before the row lock, and prove the locked compare-and-apply does not regress the newer status or assign an ineligible order. For lock contention, hold the target row in another session beyond a tiny whole-operation deadline, assert 503/rollback, release it, and prove no delayed assignment occurs.

- [ ] **Step 2: Implement bounded backend flow**

Add a take-specific provider-read deadline (default 8 seconds) and a hard whole-operation deadline (default 10 seconds) covering the read, row-lock acquisition, revalidation, flush/commit, and final reload. On either timeout, explicitly roll back and return the safe 503; cancellation must prevent any late commit. Check for the target already assigned to the same staff user and return before provider I/O. Otherwise snapshot provider ID plus local status/version timestamp without a row lock, run `get_order_status` inside the inner deadline, then acquire/reload with `FOR UPDATE` under the remaining outer deadline. Apply the provider read only when the locked row still matches the snapshot status/version; otherwise treat the locked row as authoritative. Recheck active assignment/current status/payment and commit assignment only if still eligible. Keep conflict for another active/assigned order.

- [ ] **Step 3: Add RED frontend timeout reconciliation tests**

For both staff list and detail pages, capture the original mutation start time and test timeout/no-response followed by:

- same active order -> Active tab/navigation, no false error, one POST
- different active order -> conflict/Active state, one POST
- bounded reads remain empty -> safe refresh/retry message, one POST

Include a delayed second GET case so reconciliation is not a single immediate race. Add service-level tests proving `takeStaffOrder` passes exactly `timeout: 15000`, reconciliation reads disable the Axios retry interceptor, each uses a 2000 ms timeout, and the helper stops after three attempts or cancellation.

Add a timing RED test where the connection fails immediately but the backend commits at 9.5 seconds. Require the final reconciliation read to start no earlier than 11 seconds after the original mutation start (10-second hard operation deadline plus 1-second margin), find the assignment, and never expose retry before that read completes.

- [ ] **Step 4: Implement shared bounded GET reconciliation**

Give `takeStaffOrder` an explicit 15-second timeout and record its start timestamp. Add a shared bounded helper with three target offsets from that timestamp: immediate, 5 seconds, and 11 seconds. Each active-order GET is capped at 2000 ms with interceptor retry explicitly disabled; the final read cannot start before the hard operation deadline plus 1-second margin. The helper is cancellable with `AbortSignal`, returns `same|different|none`, and may expose retry only after the final read completes (maximum about 13 seconds after an immediate disconnect). It runs only for transport/timeout ambiguity. Do not auto-repeat POST. Reuse it in list/detail pages and keep all interactive targets at least 44px. Record and verify in the runbook that provider deadline `8s < hard operation deadline 10s < client mutation timeout 15s < deployed proxy timeout`; if the proxy bound is not greater than 15 seconds, stop the release.

- [ ] **Step 5: Run and commit**

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_staff_delivery.py -q
cd frontend && npm test -- --run src/services/staffApi.test.ts src/pages/staff/StaffOrdersPage.test.tsx src/pages/staff/StaffOrderDetailPage.test.tsx
cd frontend && npm run typecheck
git add backend/app/config.py backend/app/services/staff_delivery_service.py backend/tests/api/test_staff_delivery.py frontend/src/services/api.ts frontend/src/services/staffApi.ts frontend/src/services/staffApi.test.ts frontend/src/pages/staff/StaffOrdersPage.tsx frontend/src/pages/staff/StaffOrderDetailPage.tsx frontend/src/pages/staff/*.test.tsx
git commit -m "fix: reconcile staff take order timeouts"
```

---

### Task 7: Reapply configured Telegram webhook secrets on startup

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/api/test_webhooks.py`
- Create: `backend/tests/test_start_script.py`
- Modify: `start.sh` only to validate the Bot API `ok` response if current parsing discards it
- Modify: `docs/admin-staff-table-inspection-rollout.md`

**Contract:** `getWebhookInfo` never claims to verify a secret. When a secret is configured, startup always calls `setWebhook`; matching URL/update optimization applies only when no secret is configured. A configured-secret registration failure aborts startup rather than exposing a healthy backend that rejects Telegram. A successful HTTP response with Bot API `ok=false` is a failure in both Python startup and `start.sh`.

- [ ] **Step 1: Replace wrong skip test with RED tests**

Add:

- `test_register_telegram_webhook_sets_when_url_matches_and_secret_is_configured`
- `test_register_telegram_webhook_skips_matching_url_only_when_secret_is_empty`
- `test_register_telegram_webhook_reapplies_changed_secret`
- `test_register_telegram_webhook_rejects_bot_api_ok_false`
- `test_register_telegram_webhook_configured_secret_failure_aborts_startup`

Ensure secrets are fixtures only and never captured in logs.

- [ ] **Step 2: Implement write-only secret behavior**

Only return early for matching observable fields when `telegram_webhook_secret` is empty. Otherwise POST the configured payload on every startup and validate HTTP plus JSON `ok is True`. On any configured-secret registration failure, log only a bounded category and re-raise so FastAPI startup/readiness fails. Keep logs URL-only/safe.

In `start.sh`, add a sourceable JSON validator that requires root `ok is true` without printing the body/secrets, and make every Telegram helper call pass through it. Add `backend/tests/test_start_script.py` subprocess tests that source the helper-only mode and prove HTTP-200 `{"ok":false}` returns nonzero while `{"ok":true}` succeeds; `bash -n` alone is not evidence.

- [ ] **Step 3: Document rotation boundary**

State that this release freezes current secret values and **prohibits rotation** because dual-secret acceptance is not implemented. Record old+next acceptance as a future design requirement only, not an executable current procedure. Do not claim `getWebhookInfo` verifies a secret.

- [ ] **Step 4: Run and commit**

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_webhooks.py tests/test_start_script.py -q
bash -n start.sh
git add backend/app/main.py backend/tests/api/test_webhooks.py backend/tests/test_start_script.py start.sh docs/admin-staff-table-inspection-rollout.md
git commit -m "fix: reapply Telegram webhook secrets"
```

---

### Task 8: Close exact-candidate rollout gates

**Files:**
- Modify: `backend/tests/test_admin_user_service.py`
- Modify: `docs/admin-staff-table-inspection-rollout.md`
- Modify: `.github/workflows/ci.yml`

**Contract:** The final-admin concurrency test proves exactly one success, one HTTP 409, and one remaining admin. The release gate runs it in a disposable database and fails on skip. Production deployment blocks on legacy pending Rahmat delivery rows after old writers are quiesced. No secret rotation or online-table-payment enablement occurs in this release.

- [ ] **Step 1: Strengthen concurrency assertions and isolation guard with RED guard tests**

Add pure guard tests that reject a remote host, the shared/default `restaurant_db`, and incidental marker names such as `contest-production`; accept only loopback plus exact prefix `admin_concurrency_gate_` with `RUN_DESTRUCTIVE_POSTGRES_TESTS=1`. Require that explicit opt-in and fail rather than silently skip when it is set with an unsafe target. Assert exactly one successful demotion and one `HTTPException` with status 409/detail `Cannot remove the final admin role.`, plus one admin remaining.

- [ ] **Step 2: Run the targeted proof once without rebuilding Docker**

Run one fresh volume-free `postgres:16-alpine` container with a random loopback-only port and generated non-production credentials; do not attach a named/bind volume. Install a shell cleanup trap that always removes the container. Export the settings the application actually reads: `POSTGRES_HOST=127.0.0.1`, the discovered `POSTGRES_PORT`, generated `POSTGRES_USER`/`POSTGRES_PASSWORD`, `POSTGRES_DB=admin_concurrency_gate_<nonce>`, and `RUN_DESTRUCTIVE_POSTGRES_TESTS=1`. Run only `tests/test_admin_user_service.py::test_concurrent_admin_demotions_do_not_remove_all_admins --junitxml=/tmp/admin-concurrency-gate.xml`. Parse the XML with the backend virtualenv's Python standard library and require exactly `tests=1`, `failures=0`, `errors=0`, `skipped=0`; then let the trap destroy the container. Do not point this test at the existing local PostgreSQL volume, `restaurant_db`, or production. This is the one permitted disposable Docker test and performs no application image rebuild.

Use these exact local commands from `backend/` (the password is disposable test data):

```bash
set -euo pipefail
GATE_NONCE="$(date -u +%Y%m%d%H%M%S)-$$"
GATE_CONTAINER="admin-concurrency-gate-$GATE_NONCE"
GATE_DB="admin_concurrency_gate_${GATE_NONCE//-/_}"
GATE_USER=gate_user
GATE_PASSWORD=gate_password_only
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
  .venv/bin/python -m pytest \
    tests/test_admin_user_service.py::test_concurrent_admin_demotions_do_not_remove_all_admins \
    -q --junitxml=/tmp/admin-concurrency-gate.xml

.venv/bin/python -c '
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
totals = tuple(sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped"))
assert totals == (1, 0, 0, 0), totals
' /tmp/admin-concurrency-gate.xml

docker stop --time 30 "$GATE_CONTAINER" >/dev/null
trap - EXIT INT TERM
```

Add a dedicated `Admin concurrency gate` CI job with its own PostgreSQL service database named `admin_concurrency_gate_ci`. Its job environment must set `POSTGRES_HOST=localhost`, the service user/password/database, `TELEGRAM_BOT_TOKEN=test_token`, `JWT_SECRET=test_secret`, `ALIPOS_API_CLIENT_ID=test_client_id`, `ALIPOS_API_CLIENT_SECRET=test_client_secret`, `ALIPOS_RESTAURANT_ID=test-restaurant-id`, and `RUN_DESTRUCTIVE_POSTGRES_TESTS=1`. Run the targeted test/JUnit command plus the same `tests=1/failures=0/errors=0/skipped=0` assertion. The broad backend job may still skip the destructive test; the dedicated job is mandatory for exact-SHA release approval.

- [ ] **Step 3: Add an exclusive legacy-pending cutover gate**

Update the runbook with this single observable cutover sequence while the exclusive release freeze is held:

1. Recreate only Caddy with a temporary archived Compose override whose first route returns 503 for exactly `POST /api/orders`; keep all GETs and provider webhook routes forwarded to the still-running old backend. Verify an external/local POST receives the maintenance 503 and webhook/health paths still reach the backend. Do not modify the Git checkout's Caddyfile.
2. Keep the old backend running for a fixed 600-second drain interval, exceeding the production-base worst-case sequential provider timeout/retry/backoff chain plus margin. New creates remain blocked while callbacks and already admitted requests can complete.
3. Stop the old backend with a 180-second graceful timeout. Require `OOMKilled=false` and exit code `0`; exit code 137, timeout, signal/forced termination, or any uncertain drain aborts the release and forbids trusting either DB gate until provider-side reconciliation is completed.
4. Run the first legacy-pending zero gate using only production-base columns.
5. If nonzero, restore/restart the archived old backend behind the still-active create-maintenance route, verify health, record the aborted freeze, and stop; do not continue.
6. Apply the additive migrations once in chronological order while the old backend remains stopped.
7. Backfill `alipos_sync_status='synced'` only where `alipos_order_id IS NOT NULL AND alipos_sync_status IS NULL`.
8. Run the same zero gate again and require zero.
9. Keep the create-maintenance route active, the old backend stopped, and the freeze held until the exact candidate backend is healthy. Then restore the archived normal Caddy Compose source without a build, verify health, and only then admit new order POSTs. If migration/backfill/deploy fails, follow the documented compatible-old-backend recovery or rollback path before restoring traffic.

Use this exact gate for both checks:

```sql
SELECT count(*)
FROM orders
WHERE discriminator = 'delivery'
  AND payment_method = 'rahmat'
  AND payment_provider = 'multicard'
  AND payment_status = 'pending'
  AND alipos_order_id IS NOT NULL;
```

Require zero. Do not auto-cancel, charge, or resubmit these rows. Keep the narrow callback compatibility branch as defense in depth. The runbook must contain the exact maintenance Caddyfile/override, Compose validation/recreate commands, 600-second bounded drain, graceful-stop exit assertions, restoration commands, and abort path; it must not place production migrations before this stop/drain sequence or claim a count taken while order-create ingress is open is authoritative.

- [ ] **Step 4: Update exact candidate verification commands**

Require backend full tests with the targeted destructive test separately proven as passed, Ruff, frontend full tests/typecheck/build/lint, all migrations twice, Compose config, branch/rules authority, exact-SHA CI, browse-only menu gate, payment flag false, clean diff/status, and responsive role/language/browser matrix. Avoid repeated Docker rebuilds; build once only when the final exact SHA changes runtime files.

- [ ] **Step 5: Run docs/syntax tests and commit**

```bash
git diff --check
bash -n start.sh
pandoc docs/admin-staff-table-inspection-rollout.md -o /tmp/admin-staff-table-inspection-rollout.html
git add backend/tests/test_admin_user_service.py docs/admin-staff-table-inspection-rollout.md .github/workflows/ci.yml
git commit -m "docs: close table inspection release safety gates"
```

---

### Task 9: Whole-release review, exact-candidate verification, and production rollout

**Files:** No implementation file should change during verification. Any fix creates a new exact candidate and restarts this task.

- [ ] **Step 1: Request independent whole-release review**

Review the entire diff from production base through HEAD, not only the last commit. Require explicit review of provider state transitions, transaction boundaries, callback races, legacy cutover, log redaction, price consent, staff timeout reconciliation, accessibility, polling lifecycle, migration/runbook rollback, and table-inspection scope.

- [ ] **Step 2: Run fresh exact-candidate gates**

```bash
cd backend && .venv/bin/python -m pytest -q
cd backend && .venv/bin/ruff check .
cd frontend && npm test -- --run
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run lint
git diff --check
git status --short
git rev-parse HEAD
```

Also run every migration twice against local PostgreSQL, the disposable final-admin proof, Compose config, runbook sanitizer/gates, and the 18-case staff/admin language/viewport browser matrix. Record the exact SHA and outputs.

- [ ] **Step 3: Push only the reviewed exact SHA and wait for exact-SHA CI**

Push `codex/admin-staff-table-inspection`. Confirm required checks report success for the exact candidate SHA. If any commit changes, discard stale evidence and rerun the affected gates/review.

- [ ] **Step 4: Execute the production runbook once**

Perform read-only preflight and archive rollback state. Enter the exclusive freeze, install and verify the temporary order-create maintenance route, wait the full 600-second drain with the old backend still serving callbacks, and require a clean graceful old-backend exit. Run the first zero legacy-pending gate, apply migrations, run the exact sync backfill, run the second zero gate, and only then start the exact reviewed candidate. Keep the maintenance route and freeze held across the entire stopped-old-backend window; restore normal Caddy routing only after candidate health. Deploy with no opportunistic rebuild loop, then verify health/read-only smoke/webhook status/table workspace and watch bounded logs/metrics. Keep table online payment disabled and keep all secret values unchanged.

- [ ] **Step 5: Roll back on any stop condition**

Use the archived PRE compose source and exact one-operation four-service restore. Do not rebuild during incident rollback. Restore traffic only after health and compatibility checks pass.
