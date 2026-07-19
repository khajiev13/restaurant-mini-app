# AliPOS In-Place Total Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make QR table orders reach AliPOS with the food subtotal AliPOS expects, preserve the customer payable total for Multicard, and make table online payment a controlled rollout.

**Architecture:** The local order remains the financial source of truth for the customer-facing payable amount, including the hall service percentage. The AliPOS adapter derives a separate integration total: `items_cost` for `inplace`, because AliPOS applies the hall service fee, and `total_amount` for `delivery`. A backend capability gate controls table online checkout; the authenticated profile exposes only the computed boolean and the frontend renders from that capability.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic Settings, httpx, PostgreSQL, pytest, React, TypeScript, Zustand, Vitest.

## Global Constraints

- For `inplace`, AliPOS `paymentInfo.total` must equal `order.items_cost`; AliPOS applies the hall service fee.
- For `delivery`, AliPOS `paymentInfo.total` must remain `order.total_amount`.
- The local `order.total_amount` and the Multicard invoice amount remain service-inclusive.
- `INPLACE_ONLINE_PAYMENT_ENABLED` defaults to `false`; `INPLACE_ONLINE_PAYMENT_TEST_TELEGRAM_IDS` defaults to an empty CSV.
- Table online payment is allowed only when the global flag is true or the authenticated user's Telegram ID is in the parsed tester allowlist.
- Existing idempotent requests must remain readable even if the rollout gate is later disabled; no new or retried in-place invoice may be created while capability is false.
- Never log or persist AliPOS response bodies, credentials, tokens, customer data, or complete request payloads.
- A definite AliPOS HTTP rejection stores only `AliPOS rejected the order (HTTP N)` and returns a generic customer-safe 502 message.
- An unknown AliPOS create outcome becomes `SYNC_UNKNOWN` and is never automatically retried or refunded.
- A paid order that receives a definite pre-submit or AliPOS rejection queues exactly one full refund through the existing durable refund flow.
- An order found in `sending` without an AliPOS order ID during startup becomes `SYNC_UNKNOWN`; it is never re-submitted.
- The frontend must hide table online payment without the backend capability and must keep cash selected.
- No database migration is required.

---

### Task 1: AliPOS integration amount and outcome safety

**Files:**
- Modify: `backend/app/services/alipos_api.py`
- Modify: `backend/app/services/order_service.py`
- Test: `backend/tests/test_order_service.py`
- Test: `backend/tests/api/test_orders_create.py`

**Interfaces:**
- Consumes: existing `Order.items_cost`, `Order.total_amount`, `Order.discriminator`, refund fields, and `multicard_api.refund_payment`.
- Produces: `_alipos_integration_total(order: Order) -> Decimal`, status-only `AliPOSRejected.status_code`, safe lifecycle logs, and startup recovery for interrupted sends.

- [ ] **Step 1: Write failing subtotal regression tests**

Change the existing cash table assertion and add a delivery assertion so the two integration totals cannot regress:

```python
assert payload["paymentInfo"] == {
    "paymentId": CASH_PAYMENT_ID,
    "itemsCost": 36000.0,
    "total": 36000.0,
    "deliveryFee": 0.0,
}
assert float(order.total_amount) == 39600

delivery = SimpleNamespace(
    discriminator="delivery",
    items_cost=Decimal("36000"),
    total_amount=Decimal("41000"),
)
assert _alipos_integration_total(delivery) == Decimal("41000")
```

- [ ] **Step 2: Run the subtotal tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_order_service.py::test_cash_inplace_order_submits_verified_table_and_service_total -q`

Expected: FAIL because AliPOS receives `39600.0` instead of `36000.0`.

- [ ] **Step 3: Implement the integration-only amount**

```python
def _alipos_integration_total(order: Order) -> Decimal:
    if order.discriminator == "inplace":
        return Decimal(str(order.items_cost))
    return Decimal(str(order.total_amount))
```

Use `float(_alipos_integration_total(order))` only for `paymentInfo.total`; leave local totals and `_create_order_invoice(... amount_tiyin=int(order.total_amount * 100))` unchanged.

- [ ] **Step 4: Write failing tests for safe definite and unknown outcomes**

Add tests that construct a response body containing `"customer-secret"`, raise a 400 through `alipos_api.create_order`, and assert:

```python
assert exc.value.status_code == 400
assert "customer-secret" not in str(exc.value)
assert order.alipos_sync_error == "AliPOS rejected the order (HTTP 400)"
assert order.status == "SUBMISSION_FAILED"
assert "customer-secret" not in caplog.text
```

Add an interrupted-send recovery test:

```python
order.alipos_sync_status = "sending"
order.alipos_order_id = None
await db_session.commit()
recovered = await recover_interrupted_alipos_orders(db_session)
await db_session.refresh(order)
assert recovered == 1
assert order.alipos_sync_status == "unknown"
assert order.status == "SYNC_UNKNOWN"
```

- [ ] **Step 5: Run the safety tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_order_service.py -k 'rejected or interrupted or unknown' -q`

Expected: FAIL because `AliPOSRejected` currently includes the raw body and interrupted sends are not recovered.

- [ ] **Step 6: Implement status-only errors, structured safe logs, and interrupted-send recovery**

```python
class AliPOSRejected(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"AliPOS rejected the order (HTTP {status_code})")


def _alipos_log_fields(order: Order) -> dict[str, object]:
    return {
        "local_order_id": str(order.id),
        "discriminator": order.discriminator,
        "payment_kind": "cash" if order.payment_method == "cash" else "online",
        "items_cost": float(order.items_cost),
        "payable_total": float(order.total_amount),
        "integration_total": float(_alipos_integration_total(order)),
        "service_percent": float(order.service_percent or 0),
    }
```

Emit `alipos_submit_start`, `alipos_submit_synced`, `alipos_submit_rejected`, or `alipos_submit_unknown` with only these fields plus HTTP status for a definite rejection. Change `create_order` to raise `AliPOSRejected(exc.response.status_code)` without formatting the response body. Add `recover_interrupted_alipos_orders(db)` to lock rows with `alipos_sync_status == "sending"` and no `alipos_order_id`, mark them unknown, and call it before queued recovery at startup.

- [ ] **Step 7: Queue one refund only for paid definite failures**

Use the existing durable fields and dispatcher:

```python
def _queue_paid_submission_refund(order: Order) -> bool:
    if order.payment_status != "paid" or order.refund_sync_status is not None:
        return False
    order.payment_status = "refund_pending"
    order.refund_sync_status = "queued"
    order.refund_sync_error = None
    return True
```

After persisting a definite build/rejection/invalid-response failure, dispatch `_dispatch_queued_refund(db, order.id)` only when this helper returned true. Do not refund unknown outcomes. Tests must assert one provider DELETE for a paid definite rejection, zero for cash/unpaid rejection, and zero for unknown AliPOS outcome.

- [ ] **Step 8: Run focused backend tests and verify GREEN**

Run: `cd backend && .venv/bin/pytest tests/test_order_service.py tests/api/test_orders_create.py tests/api/test_webhooks.py -q`

Expected: PASS with zero failures and no secret response text in captured logs or API responses.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/app/services/alipos_api.py backend/app/services/order_service.py backend/tests/test_order_service.py backend/tests/api/test_orders_create.py backend/tests/api/test_webhooks.py
git commit -m "fix: submit table subtotal to AliPOS"
```

---

### Task 2: Controlled backend rollout for table online payment

**Files:**
- Modify: `.env.example`
- Modify: `backend/app/config.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/users.py`
- Modify: `backend/app/services/order_service.py`
- Test: `backend/tests/test_config.py`
- Test: `backend/tests/api/test_users.py`
- Test: `backend/tests/test_order_service.py`
- Test: `backend/tests/api/test_orders_status.py`

**Interfaces:**
- Consumes: `Settings._split_csv`, authenticated `User.telegram_id`, order create and retry paths.
- Produces: `can_use_inplace_online_payment(user: User) -> bool` and `UserResponse.inplace_online_payment_enabled: bool`.

- [ ] **Step 1: Write failing configuration and capability tests**

```python
monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "7301, invalid, 7302")
assert settings.inplace_online_payment_test_ids == {7301, 7302}
assert can_use_inplace_online_payment(User(telegram_id=7301, first_name="Tester"))
assert not can_use_inplace_online_payment(User(telegram_id=9999, first_name="Customer"))
```

For `/users/me`, assert the response contains `"inplace_online_payment_enabled": true` for an allowlisted user and never contains the allowlist itself.

- [ ] **Step 2: Run capability tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_config.py tests/api/test_users.py -q`

Expected: FAIL because the settings, computed field, and helper do not exist.

- [ ] **Step 3: Implement configuration, helper, and profile field**

```python
class Settings(BaseSettings):
    inplace_online_payment_enabled: bool = False
    inplace_online_payment_test_telegram_ids: str = ""

    @property
    def inplace_online_payment_test_ids(self) -> set[int]:
        result: set[int] = set()
        for raw_id in _split_csv(self.inplace_online_payment_test_telegram_ids):
            try:
                result.add(int(raw_id))
            except ValueError:
                continue
        return result


def can_use_inplace_online_payment(user: User) -> bool:
    return (
        settings.inplace_online_payment_enabled
        or user.telegram_id in settings.inplace_online_payment_test_ids
    )
```

Add `inplace_online_payment_enabled: bool = False` to `UserResponse`; in both `/users/me` responses, build the Pydantic model, set the field from the helper, and dump it. Add both environment keys with safe disabled defaults to `.env.example`.

- [ ] **Step 4: Write failing create/retry gate tests**

Assert a new `inplace` + `rahmat` request from a non-capable user raises `CustomerOrderError("Online payment is not available for table orders")` before `multicard_api.create_invoice` is called. Assert delivery Rahmat remains allowed, allowlisted in-place Rahmat creates its invoice, an existing idempotent order is returned, and `retry_customer_order_payment` blocks a new invoice after capability is disabled.

- [ ] **Step 5: Run gate tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_order_service.py tests/api/test_orders_status.py -k 'online or capability or retry' -q`

Expected: FAIL because in-place invoices are currently created without a rollout decision.

- [ ] **Step 6: Implement authoritative create and retry gates**

After the existing idempotency lookup and before table resolution, pricing, persistence, or provider calls:

```python
if (
    body.discriminator == "inplace"
    and body.payment_method == "rahmat"
    and not can_use_inplace_online_payment(current_user)
):
    raise CustomerOrderError("Online payment is not available for table orders")
```

In `retry_customer_order_payment`, apply the same capability check before `_create_order_invoice`. Do not block Multicard callbacks or refunds for already-created orders.

- [ ] **Step 7: Run Task 2 tests and verify GREEN**

Run: `cd backend && .venv/bin/pytest tests/test_config.py tests/api/test_users.py tests/test_order_service.py tests/api/test_orders_status.py -q`

Expected: PASS with zero failures.

- [ ] **Step 8: Commit Task 2**

```bash
git add .env.example backend/app/config.py backend/app/schemas/user.py backend/app/routers/users.py backend/app/services/order_service.py backend/tests/test_config.py backend/tests/api/test_users.py backend/tests/test_order_service.py backend/tests/api/test_orders_status.py
git commit -m "feat: gate table online payment rollout"
```

---

### Task 3: Capability-aware table checkout UI

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx`

**Interfaces:**
- Consumes: authenticated profile field `User.inplace_online_payment_enabled`.
- Produces: cash-only table checkout when false and unchanged cash/Rahmat delivery checkout.

- [ ] **Step 1: Write failing UI tests**

Extend the mocked auth state with `user`. For a table order and capability false, assert no button matching `/karta|online/i` exists and the submitted method is cash. For capability true, preserve the existing immediate checkout test. For delivery, assert both methods remain visible regardless of the table capability.

```typescript
authState.user = { telegram_id: 7301, inplace_online_payment_enabled: false };
expect(screen.queryByRole('button', { name: /karta|online/i })).not.toBeInTheDocument();

authState.user = { telegram_id: 7301, inplace_online_payment_enabled: true };
expect(await screen.findByRole('button', { name: /karta|online/i })).toBeVisible();
```

- [ ] **Step 2: Run UI tests and verify RED**

Run: `cd frontend && npm test -- ArtisanCheckoutPage.test.tsx`

Expected: FAIL because table checkout always renders Rahmat.

- [ ] **Step 3: Implement capability-aware rendering**

```typescript
const user = useAuthStore((state) => state.user);
const canPayOnline = !isTableOrder || user?.inplace_online_payment_enabled === true;
const paymentMethods = canPayOnline
  ? PAYMENT_METHODS
  : PAYMENT_METHODS.filter((method) => method.key === 'cash');
```

Render `paymentMethods`. Add `inplace_online_payment_enabled: boolean` to `User`. Add a defensive effect that changes `rahmat` back to `cash` if a table capability becomes false, using primitive dependencies only.

- [ ] **Step 4: Run focused frontend tests and verify GREEN**

Run: `cd frontend && npm test -- ArtisanCheckoutPage.test.tsx stores/__tests__/authStore.test.ts`

Expected: PASS with zero failures.

- [ ] **Step 5: Run TypeScript build and commit Task 3**

Run: `cd frontend && npm run build`

Expected: exit code 0.

```bash
git add frontend/src/types/api.ts frontend/src/pages/artisan/ArtisanCheckoutPage.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx
git commit -m "feat: hide gated table online checkout"
```

---

### Task 4: Whole-system verification and production deployment

**Files:**
- Verify: all branch changes against `docs/superpowers/specs/2026-07-13-alipos-inplace-total-validation-design.md`
- Modify only if verification or review exposes a defect.

**Interfaces:**
- Consumes: Tasks 1-3 commits.
- Produces: reviewed exact commit deployed with global table online payment disabled and empty tester allowlist.

- [ ] **Step 1: Run complete local verification**

Run:

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm test
npm run build
cd .. && docker compose config --quiet
git diff --check
```

Expected: all commands exit 0, all backend and frontend tests pass, and the production build succeeds.

- [ ] **Step 2: Request an independent whole-branch review**

Give the reviewer the plan, approved design, test evidence, and full merge-base diff. Fix every Critical or Important finding, rerun the covering tests, and repeat review until both spec compliance and code quality are approved.

- [ ] **Step 3: Push the reviewed exact commit**

Run: `git push -u origin codex/alipos-inplace-total-fix`

Expected: the remote branch points to the locally verified HEAD.

- [ ] **Step 4: Run production preflight before changing containers**

On the WSL host, back up PostgreSQL and current SHA, verify zero unexpired pending in-place invoices, set `INPLACE_ONLINE_PAYMENT_ENABLED=false` and `INPLACE_ONLINE_PAYMENT_TEST_TELEGRAM_IDS=` without displaying secrets, fetch the branch, and detach at the reviewed exact commit.

- [ ] **Step 5: Prebuild, deploy, and verify production**

Run on the host:

```bash
docker compose build backend frontend
./start.sh
docker compose ps
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS https://restaurant.labtutor.app/healthz
curl -fsS https://restaurant.labtutor.app/api/health
docker compose logs --since=10m backend
```

Expected: all nine containers are running, health-reporting containers are healthy, all four health requests return 200, the server SHA equals reviewed HEAD, and logs contain no raw AliPOS response body.

- [ ] **Step 6: Monitor one designated cash table retry**

Tell the user the system is ready, then tail backend logs while the designated customer orders. Success requires HTTP 200 from `POST /api/orders`, `alipos_submit_synced`, AliPOS order ID persisted, correct table ID, and no Multicard invoice.
