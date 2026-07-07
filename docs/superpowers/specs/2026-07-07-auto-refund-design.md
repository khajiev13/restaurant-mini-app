# Auto Refund For Unaccepted Rahmat Orders

Date: 2026-07-07
Status: Draft for review

## Summary

Implement a Meituan-style cancellation and refund flow for Rahmat/Multicard orders that are paid online but not accepted by the restaurant. The app should let the user cancel and receive a full refund while the AliPOS order is still `NEW`, and should automatically cancel and refund the order if it remains `NEW` for 10 minutes after payment confirmation.

This spec intentionally does not cover post-acceptance disputes, partial refunds, food-quality complaints, or support escalation. Those are larger marketplace workflows and should be designed separately.

## Research Baseline

Meituan Waimai and Ele.me both use restaurant acceptance as the main boundary:

- Before merchant acceptance, users can cancel directly and paid orders are automatically refunded.
- If the merchant does not accept in a short window, the system auto-cancels and auto-refunds. Meituan and Ele.me public materials use 5 minutes as the reference point.
- After merchant acceptance, cancellation becomes merchant-reviewed or support-mediated, because the restaurant may have started preparing food.

For our product, we will use the same state boundary but a longer timeout:

- While the order remains `NEW`: user-initiated cancellation/refund is allowed.
- If the order is still `NEW` 10 minutes after payment: system cancellation/refund runs automatically.
- `ACCEPTED_BY_RESTAURANT` and later: user-initiated and automatic refund close for this version.

Multicard supports full refunds with:

```http
DELETE /payment/{uuid}
Authorization: Bearer <token>
```

The required UUID is the paid Multicard transaction UUID saved as `orders.multicard_payment_uuid`. A successful full refund returns a `PaymentModel` whose status is expected to become `revert`.

## Goals

- Protect users who place paid orders when the restaurant is closed, inattentive, or unable to accept.
- Refund through the original Rahmat/Multicard payment path, not store credit.
- Keep cancellation eligibility simple and explainable: paid + unaccepted.
- Make refund operations idempotent and auditable.
- Avoid repeated provider refund calls when the provider result is ambiguous.
- Preserve the restaurant-facing AliPOS order state by cancelling the AliPOS order when we cancel/refund.

## Non-Goals

- Partial refunds.
- Refunds after `ACCEPTED_BY_RESTAURANT`.
- Admin dashboard workflows.
- Merchant dispute resolution.
- Switching to Multicard hold/authorize-capture.
- Reworking the overall payment-order sequence.

## Current System Context

The current app creates an AliPOS order first, then creates a Multicard invoice for Rahmat payments. The local order starts as `status="NEW"` and Rahmat payment starts as `payment_status="pending"`.

Multicard callback stores:

- `payment_status="paid"`
- `payment_paid_at`
- `multicard_payment_uuid`
- receipt/payment card metadata

The app already has an unpaid-payment expiry worker. It marks old pending Rahmat orders as expired, cancels the unpaid Multicard invoice, and best-effort cancels the AliPOS order. It does not handle paid refunds.

The order status path has a risk that matters for this feature: AliPOS webhook handling and status polling both write `order.status` directly. The refund implementation should introduce one shared status-transition service so cancellation/refund state is not accidentally overwritten by stale polling or webhook updates.

## User-Facing Behavior

### Pending Payment

If a Rahmat order is still `payment_status="pending"`:

- Show the current "Pay with Rahmat" action.
- Add a secondary "Cancel order" action.
- On confirmation, cancel the unpaid Multicard invoice and AliPOS order.
- Set local order state to `status="CANCELLED"` and `payment_status="expired"` with a user-cancelled-before-payment reason.
- No refund is issued because the payment has not completed.

### Paid But Unaccepted

If a Rahmat order is:

- `payment_status="paid"`
- `order.status="NEW"`
- `multicard_payment_uuid` is present

then the order is eligible for full cancellation/refund.

The user can tap "Cancel and refund" from the order status page. The app must show a Telegram confirmation before sending the request. If accepted, the backend cancels the AliPOS order and performs a full Multicard refund.

### Automatic Timeout Refund

If a Rahmat order remains:

- `payment_status="paid"`
- `order.status="NEW"`
- `payment_paid_at <= now - 10 minutes`
- no completed/pending refund already exists

then the backend auto-cancels and auto-refunds it.

The 10-minute timer starts at `payment_paid_at`, not at order creation, because the user should not be penalized for time spent completing payment.

### After Restaurant Acceptance

Once the order reaches `ACCEPTED_BY_RESTAURANT` or a later status, the user-facing refund action is hidden for this version and the automatic refund worker must skip the order.

If the restaurant later cancels or cannot fulfill, that should be handled by a separate merchant/admin or support flow.

## Backend Design

### Refund Service

Add a service responsible for refund orchestration. It should be the only place that performs a paid refund.

Responsibilities:

- Validate eligibility.
- Lock the order row before changing refund state.
- Mark refund as pending before calling Multicard.
- Cancel the AliPOS order best-effort.
- Call Multicard full refund using `multicard_payment_uuid`.
- Persist success or failure with provider details.
- Return existing state without a new provider call when the refund is already pending or succeeded.

Recommended high-level flow:

1. Load order for update.
2. Reject if order is not Rahmat/Multicard paid.
3. Reject if order status is not `NEW`.
4. Reject if missing `multicard_payment_uuid`.
5. If refund already pending or succeeded, return current order.
6. Mark `refund_status="pending"` with actor/reason/request id.
7. Commit the pending state.
8. Best-effort cancel AliPOS order.
9. Call Multicard `DELETE /payment/{uuid}`.
10. If success and provider status is `revert`, set `refund_status="succeeded"`, `payment_status="refunded"`, `status="CANCELLED"`.
11. If provider response is an explicit failure, set `refund_status="failed"` and keep retry data.
12. If provider call times out or result is ambiguous, poll `GET /payment/{uuid}` before retrying a refund call.

### User Endpoint

Add an authenticated endpoint under `/api/orders/{order_id}/refund` or `/api/orders/{order_id}/cancel`.

Recommended naming:

```http
POST /api/orders/{order_id}/refund
```

Request body:

```json
{
  "reason": "Restaurant has not accepted the order"
}
```

The backend derives actor type/id from the authenticated user. The client must not send actor fields.

Response should reuse `OrderResponse` with refund fields included.

### Automatic Worker

Add a startup background worker similar to the existing payment-expiry task.

Selection criteria:

```text
payment_provider = "multicard"
payment_status = "paid"
status = "NEW"
payment_paid_at <= now - refund_unaccepted_timeout_seconds
refund_status is null or refund_status = "failed"
```

The timeout should be configurable:

```env
REFUND_UNACCEPTED_TIMEOUT_SECONDS=600
REFUND_CHECK_INTERVAL_SECONDS=30
```

Use a Postgres advisory lock so multiple backend instances do not process the same refund batch.

### Status Transition Service

Create a shared helper for applying AliPOS status updates from both webhook and polling paths.

Minimum behavior:

- Normalize `CANCELED`/`CANCELLED` for our own display and checks.
- Do not overwrite local terminal cancellation/refund states with stale non-terminal statuses.
- If an AliPOS status moves an order from `NEW` to `ACCEPTED_BY_RESTAURANT`, close refund eligibility.
- Keep raw status if AliPOS sends unknown values, but avoid accidental refund eligibility for unknown states.

## Data Model

Add same-table refund fields to `orders`:

```sql
refund_status          VARCHAR(50),
refund_request_id      UUID,
refund_amount          NUMERIC(12, 2),
refund_requested_at    TIMESTAMP,
refund_completed_at    TIMESTAMP,
refund_failed_at       TIMESTAMP,
refund_error_code      VARCHAR(100),
refund_error           TEXT,
refund_actor_type      VARCHAR(32),
refund_actor_id        VARCHAR(255),
refund_reason          TEXT,
refund_gateway_status  VARCHAR(50),
refund_attempt_count   INTEGER NOT NULL DEFAULT 0
```

Recommended indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_refund_status ON orders(refund_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_refund_request_id
  ON orders(refund_request_id)
  WHERE refund_request_id IS NOT NULL;
```

Consider a partial unique index on `multicard_payment_uuid` after checking production data for duplicates.

Because this repo does not currently use Alembic, implementation must update both:

- `database/init.sql` for fresh installs.
- A separate production SQL migration for existing databases.

ORM models and Pydantic schemas must be updated too, because tests create tables from `Base.metadata.create_all`.

## Payment Provider Handling

Use Multicard full refund:

```http
DELETE /payment/{uuid}
```

Do not use invoice deletion for paid refunds:

```http
DELETE /payment/invoice/{uuid}
```

Invoice deletion only cancels unpaid invoices.

If the refund call returns a clear success:

- Store provider status, expected `revert`.
- Set `payment_status="refunded"`.
- Set `refund_status="succeeded"`.

If the refund call returns an explicit provider error:

- Store error code/details.
- Set `refund_status="failed"`.
- Keep the order visible with a "Refund failed" state.

If the call times out or the result is ambiguous:

- Poll `GET /payment/{uuid}`.
- If provider status is already `revert`, mark success.
- If provider status remains `success`, allow controlled retry from worker/admin.
- Avoid repeated immediate `DELETE` calls.

## Frontend UX

Primary surface: order status page Rahmat payment banner.

This is simple enough for v1 and does not require a separate UI designer before implementation. The existing payment banner can absorb the new actions and states using the current component style, button treatments, icon language, and Telegram confirmation pattern. A designer pass can still polish copy/spacing later, but it is not a launch dependency.

Add states:

- `pending`: awaiting payment; actions are "Pay with Rahmat" and "Cancel order".
- `paid` + `NEW`: payment confirmed; actions are "View receipt" and "Cancel and refund".
- `refund_pending`: refund requested; show a progress message and disable destructive actions.
- `refunded`: refunded; terminal state, hide progress stepper.
- `refund_failed`: refund failed; show retry/contact-support copy.

The order list and profile page should not expose the primary refund action, but they should display refund/cancelled badges correctly so refunded orders do not appear as delivered or merely placed.

Use Telegram `showConfirm` before any cancel/refund action. After the backend call, immediately refresh the order and continue polling.

## Optional UI Designer Brief

If a UI designer later reviews this, use the following brief. For v1, engineering should implement these states directly in the existing Telegram Mini App order status page. Keep the current artisan/restaurant visual language and integrate into the existing order status page rather than making a new page.

Required screens/states:

1. Rahmat payment pending:
   - Existing payment banner.
   - Primary action: "Pay with Rahmat".
   - Secondary/destructive action: "Cancel order".

2. Paid but restaurant has not accepted:
   - Payment confirmed state.
   - Show reassuring copy that the restaurant has not accepted yet.
   - Primary safe action: "View receipt".
   - Secondary/destructive action: "Cancel and refund".
   - Include text that refund returns to the original payment method.

3. Confirmation prompt:
   - Native Telegram confirmation copy for cancel/refund.
   - Short and clear: the order will be cancelled and the full amount refunded.

4. Refund pending:
   - No duplicate refund button.
   - Show that refund is being processed.
   - Mention that the app will update automatically.

5. Refunded:
   - Terminal success state.
   - Clear badge: "Refunded".
   - Explain that the money is returned through Rahmat/Multicard to the original payment method and bank/payment timing may vary.

6. Refund failed:
   - Error state.
   - Clear next step: retry if allowed or contact restaurant/support.

Constraints:

- Mobile-first inside Telegram Mini App.
- Do not use a fixed bottom refund bar unless it is tested against Telegram safe areas and existing bottom navigation.
- Use the current design system colors, typography, icons, and spacing.
- Avoid dense legal copy.
- Keep button labels short enough for English, Russian, and Uzbek.
- Order list/profile need small badges for refunded/refund-pending/refund-failed states.

Suggested button labels:

- English: "Cancel order", "Cancel and refund", "Refund processing", "Refunded"
- Russian: "Отменить заказ", "Отменить и вернуть", "Возврат обрабатывается", "Возвращено"
- Uzbek: "Buyurtmani bekor qilish", "Bekor qilish va qaytarish", "Qaytarish jarayonda", "Qaytarildi"

## API And Schema Changes

Backend response models should expose:

- `refund_status`
- `refund_requested_at`
- `refund_completed_at`
- `refund_failed_at`
- `refund_amount`
- `refund_reason`
- `refund_error` when relevant

Frontend TypeScript should replace loose payment/refund strings with unions where practical:

```ts
type PaymentStatus = "pending" | "paid" | "expired" | "refunded" | null;
type RefundStatus = "pending" | "succeeded" | "failed" | null;
```

The UI may map backend `refund_status="succeeded"` to display text "Refunded".

## Testing Strategy

Use test-driven development for implementation.

Backend tests:

- User can refund paid Rahmat order while `status="NEW"`.
- User cannot refund someone else's order.
- User cannot refund unpaid order through paid refund endpoint.
- User cannot refund after `ACCEPTED_BY_RESTAURANT`.
- Duplicate refund requests do not call Multicard twice.
- Auto worker refunds paid orders that remain `NEW` past 10 minutes.
- Auto worker does not refund paid orders accepted before timeout.
- Ambiguous Multicard timeout polls payment status before retrying.
- AliPOS webhook/polling transition does not overwrite local refunded/cancelled terminal state.

Frontend tests:

- Paid `NEW` order shows "Cancel and refund".
- Accepted order hides refund action.
- Refund pending disables duplicate actions.
- Refunded state hides normal progress stepper and shows success badge.
- Profile/order list do not label refunded orders as delivered.

Manual verification:

- Sandbox refund against a paid test transaction if available.
- Telegram Mini App confirmation behavior.
- Responsive visual check for English, Russian, and Uzbek labels.

## Risks And Mitigations

- Race between AliPOS acceptance and refund request:
  Lock the order row and re-check latest known status before refund. Optionally poll AliPOS before refund if local status is old.

- Multicard refund call timeout:
  Poll payment status before retrying. Avoid blind repeated `DELETE`.

- AliPOS cancellation fails after refund succeeds:
  Store `alipos_cancel_status="failed"` and log for operator follow-up; user should not lose refund protection.

- Multicard callback arrives after local expiry/cancel:
  Update callback logic so `expired` or cancellation states are not blindly overwritten to `paid` without evaluating refund/cancel state.

- Existing production DB does not auto-run `init.sql`:
  Provide a separate migration script and deployment note.

## Product Decisions

- User-initiated refund is allowed immediately after payment while the order is still `NEW`.
- Automatic refund runs after the order remains `NEW` for 10 minutes after `payment_paid_at`.
- User-triggered refund should poll AliPOS immediately before refunding when local order status may be stale.
- Admin retry endpoint is out of scope for v1; failed refunds remain visible for operator/manual follow-up.

## Approval Criteria

The spec is approved when the team agrees on:

- 10-minute timeout after `payment_paid_at`.
- Manual user cancellation/refund while `status="NEW"`.
- No automatic refund after `ACCEPTED_BY_RESTAURANT` in v1.
- Same-table refund fields.
- Order status transition centralization before or alongside refund implementation.
- Existing order status payment banner as the v1 UI surface, with no separate designer dependency.
