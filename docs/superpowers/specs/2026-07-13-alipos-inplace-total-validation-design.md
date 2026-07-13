# AliPOS In-place Total Validation Design

**Date:** 2026-07-13

## Goal

Make QR table orders acceptable to AliPOS while preserving the restaurant's
configured hall service charge locally, add safe production diagnostics, and
prevent unverified online table payments until the POS bill is proven to
reconcile exactly.

## Confirmed production evidence

The customer QR path, Telegram authentication, table resolution, and menu
loading succeeded. Three in-place attempts for `Stoll 1` reached order
submission with these amounts:

- Server-priced items: `4,000 UZS`.
- Hall service percentage: `10%`.
- Local customer payable total: `4,400 UZS`.
- AliPOS response: HTTP 400 because it calculated `4,000` but received
  `4,400` in `paymentInfo.total`.

No AliPOS order was created for those attempts. The first attempt created an
online invoice, but switching to cash confirmed invoice cancellation before
AliPOS submission; no successful payment was recorded.

This proves that the current AliPOS in-place validator expects the submitted
item subtotal. It does not prove whether AliPOS Desktop subsequently applies
the hall's service percentage or how an externally paid bill is reconciled.

## Amount contract

The application will keep two explicit amount meanings:

- `total_amount` remains the customer payable amount:
  `items_cost + service_charge + delivery_fee`.
- The AliPOS integration total for an in-place order is `items_cost`.
- The AliPOS integration total for a delivery order remains `total_amount`.
- `paymentInfo.itemsCost` remains `items_cost` for both order types.
- Multicard amounts, callback verification, receipts, and refunds remain based
  on `total_amount`.

For the observed order, the application will therefore show `4,400`, while
the AliPOS create payload will contain `itemsCost=4,000` and `total=4,000`.
There is no database migration and no change to persisted amount columns.

## Temporary online-payment gate

Online payment for delivery orders remains unchanged. Online payment for
in-place orders is disabled by default until the controlled POS validation is
complete.

The backend owns the gate through:

- `INPLACE_ONLINE_PAYMENT_ENABLED`, a boolean defaulting to `false` for broad
  availability.
- `INPLACE_ONLINE_PAYMENT_TEST_TELEGRAM_IDS`, an empty CSV allowlist for
  explicitly coordinated production testers.

An authenticated customer may use online table payment only when the broad
flag is true or their Telegram ID is in the test allowlist:

- New in-place orders using `rahmat` are rejected before invoice creation.
- Retrying payment for an unpaid in-place order is rejected while disabled.
- Existing pending orders may still switch safely to cash or be cancelled.
- A valid callback for a payment that already completed is still processed;
  the gate must not strand a customer who has already paid.
- Delivery order creation and payment remain unchanged; this change does not
  add a delivery payment-retry capability.

The authenticated `/users/me` response exposes only the computed safe boolean
as `inplace_online_payment_enabled`; it never exposes the allowlist. Checkout
shows only cash in table mode when this capability is false. Backend
enforcement remains authoritative even if an old frontend attempts to submit
`rahmat`.

After full validation, changing the broad setting to `true` and restarting the
backend enables the option for all authenticated table customers after their
profile is refreshed. The production test uses only the tester allowlist; the
broad flag remains false.

Neither gate invalidates a Multicard invoice that was already issued. Before
changing `false` to `true` or adding a tester, a read-only preflight must prove
there are zero unexpired pending in-place invoices. If any exist, enablement
stops until each invoice is confirmed cancelled through the existing safe
switch/cancel flow or confirmed expired by Multicard. Hiding a checkout URL is
not treated as invoice cancellation.

Disabling broad or tester access happens immediately during an incident and
must not wait for pending invoices. Already-issued invoices are then tracked
and safely cancelled or expired separately, while valid callbacks continue to
be honored so a customer who already paid is not stranded.

## Post-payment compensation

Online table payment cannot be enabled until a paid order has a safe
compensation path when AliPOS definitely did not accept it.

- A definite pre-submission failure, such as an unavailable AliPOS online
  payment method, or a definite AliPOS HTTP rejection queues a refund only
  when Multicard payment was already verified. It durably changes that paid
  order to `refund_pending` and queues exactly one full Multicard refund. The
  same failure before invoice creation or verified payment rejects checkout
  without creating a refund.
- The existing refund dispatcher makes one refund request. A definite success
  becomes `refunded`; a definite rejection becomes `refund_failed`; and a
  transport-ambiguous result becomes `unknown` and is reconciled by reading
  provider state without repeating the refund request.
- An AliPOS transport-unknown create outcome does not trigger an automatic
  refund. The order remains `SYNC_UNKNOWN` for staff review because AliPOS may
  have created it; refunding at that point could give away an accepted order.
- On startup, any order left in `sending` without an AliPOS order ID is treated
  as a process-crash unknown outcome and moved to `SYNC_UNKNOWN`. Startup does
  not retry or auto-refund it; AliPOS acceptance must be reconciled manually.
- The ordinary customer cancellation path is not used to compensate an order
  that has no AliPOS order ID.
- The payment callback remains idempotent and acknowledges a valid payment
  once its paid state and the downstream work have been durably queued.

Online table payment remains disabled while any compensating refund is failed
or unknown.

## Production diagnostics

The order service will emit structured, searchable log events around the
single AliPOS create attempt:

- `alipos_submit_start`
- `alipos_submit_synced`
- `alipos_submit_rejected`
- `alipos_submit_unknown`

Every event may include only these safe correlation fields:

- Local order UUID.
- Order discriminator (`delivery` or `inplace`).
- Payment classification (`cash` or `online`).
- `items_cost`.
- Local `payable_total`.
- AliPOS `integration_total`.
- `service_percent`.
- AliPOS HTTP status for a definite rejection.

Logs must not contain Telegram IDs, customer names, phone numbers, comments,
addresses, access tokens, OAuth credentials, payment-method IDs, table or hall
UUIDs, Multicard invoice/payment UUIDs, full AliPOS request bodies, or full
AliPOS responses. A definite rejection stores only a bounded generic category
such as `AliPOS rejected the order (HTTP 400)` in `alipos_sync_error`; raw
provider bodies are not persisted or returned to the customer. Customer APIs
return a generic restaurant-system failure message. Order creation is never
automatically retried after a transport-ambiguous outcome.

## Automated verification

The implementation follows test-driven development:

1. Change the existing in-place service test so it first fails while expecting
   local `total_amount=39,600`, AliPOS `itemsCost=36,000`, and AliPOS
   `total=36,000` for a 10% hall.
2. Add a delivery regression test proving its AliPOS total remains the full
   delivery `total_amount`.
3. Add paid-callback coverage proving Multicard verifies the service-inclusive
   amount while the later in-place AliPOS payload uses the item subtotal.
4. Add backend tests proving disabled table-online creates no order and no
   Multicard invoice, blocks in-place payment retry, and does not affect
   delivery creation or payment.
5. Add profile and authorization tests proving the computed
   `inplace_online_payment_enabled` capability is false by default, true only
   for an allowlisted tester or broad enablement, and never exposes the
   allowlist.
6. Add checkout tests proving table-online is hidden without the authenticated
   capability and cash submission is unchanged.
7. Add log-capture tests proving start, success, rejection, and unknown-outcome
   events contain the amount split and exclude provider bodies and customer
   data.
8. Add compensation tests for an unavailable online payment method and a
   definite AliPOS rejection after verified payment. Both queue one full
   refund only for a verified paid order; the equivalent pre-payment failure
   queues no refund. An AliPOS transport-unknown outcome queues no refund, and
   an ambiguous refund is reconciled without a second refund request.
9. Add rejection-sanitization tests with secret-like keys and oversized
   provider bodies, proving raw detail is absent from logs, persistence, and
   customer responses.
10. Add startup-recovery coverage proving an order stranded in `sending`
   without an AliPOS order ID becomes `SYNC_UNKNOWN` and is neither retried nor
   refunded.
11. Run the complete backend and frontend test suites, type checking, linting,
   and production builds before deployment.

## Controlled production validation

### Phase 1: cash

1. Deploy with `INPLACE_ONLINE_PAYMENT_ENABLED=false`.
2. Verify all containers, the public frontend, `/healthz`, `/api/health`, table
   resolution, and the live menu.
3. Read the current live menu and resolved hall percentage, calculate the
   expected subtotal, service charge, and payable total, and record those
   expected values without hardcoding a historical menu price.
4. Have one designated, coordinated tester rescan the QR code and order one
   inexpensive item using cash with the Uzbek test comment
   `TEST: tayyorlamang, QR buyurtma tekshiruvi`. The user's mom may be the
   designated tester after the user confirms the restaurant is ready and the
   test window is open.
5. Watch only the safe `alipos_submit_*` events and confirm the logged
   `items_cost` and `integration_total` equal the current item subtotal and the
   `payable_total` equals subtotal plus the resolved hall service charge.
6. Confirm AliPOS returns an order ID and a fresh read reports `NEW`.
7. Confirm AliPOS Desktop shows the correct table and item.
8. Ask the restaurant to inspect the final desktop bill before accepting or
   preparing the order.

The decision gate is exact:

- If Desktop shows the current item subtotal plus the expected hall service
  charge exactly once, Phase 1 passes. Cancel the order only after a fresh read
  still reports `NEW`, using a non-empty Uzbek test-cancellation comment.
- If Desktop shows only the item subtotal, keep online disabled and obtain
  AliPOS guidance for externally collecting the service charge.
- If Desktop adds service twice or produces any other amount, stop and correct
  the pricing contract before another customer test.
- If Desktop requires accepting the order before the final service-inclusive
  bill becomes visible, do not accept merely for inspection. Stop the test and
  obtain a safe staff-side preview or AliPOS guidance, because acceptance may
  make API cancellation ineligible.

### Phase 2: online

Phase 2 starts only after Phase 1 proves the final desktop bill equals the
current item subtotal plus the hall service charge. Confirm zero pending table
invoices, add exactly one designated tester to the allowlist while keeping
broad enablement false, refresh that tester's authenticated profile, and open a
time-boxed test window coordinated with the restaurant. Verify all of the
following using the current calculated amounts:

- Multicard charges exactly the service-inclusive payable total.
- The signed callback validates and records that exact amount as paid.
- AliPOS accepts the item subtotal as its in-place integration total.
- AliPOS Desktop shows the service charge exactly once, the same final bill, the
  correct online payment classification, and zero remaining balance.
- The fiscal receipt total equals the customer payment.
- A separate cancellable `NEW` test proves a full refund without staff
  payment-method correction. A transport-ambiguous refund is reconciled by
  provider-state lookup and is never blindly repeated.

Remove the tester from the allowlist immediately after the controlled attempt.
Online table payment remains disabled if any check fails or if a refund remains
failed or unknown.

## Deployment and rollback

Deployment will back up the current commit and database, run tests against the
exact candidate image, rebuild only the affected application images, and then
perform public and container health checks. The online gate stays false during
the cash test.

Before enabling broad access or adding a tester, the operator must confirm
there are zero unexpired pending in-place invoices. The immediate financial
rollback does not wait: reset `INPLACE_ONLINE_PAYMENT_ENABLED=false`, clear the
tester allowlist, and restart the backend. Track and safely resolve any invoice
that was already issued; valid callbacks remain honored. Backend enforcement
protects new customers even if a stale frontend still displays the online
option. If cash submission fails, revert the application image to the saved
commit; do not restore the database merely for an application rollback.

## Scope boundaries

This change does not add a database migration, alter delivery pricing, change
Multicard's protocol, invent an AliPOS service-charge field, automatically
retry order creation, redesign checkout, or expand table booking/occupancy
capabilities.

## Success criteria

- A cash table order with a non-zero hall service percentage is accepted by
  AliPOS with the correct table and items.
- Local UI and stored totals still show the service-inclusive payable amount.
- Safe logs make the local/AliPOS amount split and outcome visible without
  leaking customer or provider-sensitive data.
- Online table payment cannot create an invoice until explicitly enabled.
- A verified payment followed by a definite AliPOS rejection queues one full
  refund, while an unknown AliPOS create outcome never auto-refunds.
- Delivery behavior and its online payment flow remain unchanged.
- Online table payment is enabled only after POS, payment, receipt, and refund
  totals reconcile exactly.
