# Table Online Payment Global Enablement Design

**Date:** 2026-07-18

## Goal

Enable the existing Multicard online-payment option for every authenticated
table-order customer without changing delivery checkout or the established
AliPOS amount contract.

## Existing implementation

The deployed table-payment implementation already has a backend-owned rollout
gate. The authenticated profile exposes only the computed capability, the
frontend hides online table payment when that capability is false, and the
order service rejects an unauthorized online table order before creating a
Multicard invoice. Delivery online payment is independent of this gate.

The amount contract remains:

- `items_cost` is the food subtotal;
- `service_percent` is resolved dynamically from the selected table's current
  AliPOS hall record returned by `halls-and-tables`; it is never a configured or
  hard-coded checkout percentage;
- `total_amount` is the customer payable total, including the hall service
  charge;
- Multicard invoice creation, callback verification, receipts, cancellations,
  and refunds use `total_amount`;
- AliPOS in-place `paymentInfo.itemsCost` and `paymentInfo.total` use
  `items_cost` because AliPOS rejected the service-inclusive integration total;
- AliPOS delivery submission continues to use its existing delivery total.

The backend re-resolves the signed table against the current AliPOS directory
when creating the order, computes the service charge from that hall's returned
percentage, and persists the percentage used for the order. The percentage in
the browser table context is display-only and is not trusted for payment
pricing. Multicard receives only the resulting server-calculated
`total_amount`.

For example, if AliPOS currently returns a 10% service percentage for the hall,
a 4,000 UZS item subtotal produces a 4,400 UZS Multicard charge while AliPOS
receives 4,000 UZS for the in-place integration total. If AliPOS returns a
different percentage, the calculated service charge and Multicard total change
accordingly.

## Selected approach

Set `INPLACE_ONLINE_PAYMENT_ENABLED=true` in the existing production
environment and recreate only the backend service so the setting is loaded.
Keep the feature-gate code and the per-user tester allowlist in place. This
preserves backend enforcement, permits an immediate global rollback, and
avoids an unnecessary application-code change.

Removing the gate is rejected because it weakens rollback and stale-frontend
protection. Using only the tester allowlist is rejected because the approved
scope is global availability.

## Safe preflight

Before changing the flag:

1. Confirm the production checkout is on the implementation that contains the
   in-place subtotal fix and table-online capability gate.
2. Confirm the application stack is healthy.
3. Confirm there are no unresolved unexpired in-place invoices and no table
   payment refunds in a failed or unknown state.
4. Confirm the existing production setting is disabled.

The checks must not print credentials, tokens, customer data, complete payment
records, or provider payloads.

## Rollout

1. Back up the production environment file without displaying its contents.
2. Change only `INPLACE_ONLINE_PAYMENT_ENABLED` to `true`.
3. Recreate only the backend container; do not rebuild or restart PostgreSQL.
4. Confirm backend and public health checks pass.
5. Refresh an authenticated customer profile and confirm
   `inplace_online_payment_enabled=true`.
6. Confirm table checkout renders both Cash and Online while delivery checkout
   remains unchanged.

## Verification

Automated verification must prove the candidate code still:

- charges the service-inclusive total through Multicard;
- resolves the current hall service percentage from AliPOS and calculates the
  payable total on the backend without trusting a client-supplied percentage;
- verifies callbacks against the same total;
- sends the item subtotal to AliPOS for in-place orders;
- preserves the delivery total;
- rejects online table checkout when the flag is false and exposes it when the
  flag is true.

The production smoke test uses one inexpensive table order and first reads the
current hall percentage from AliPOS. It then derives the expected service
charge and payable total from that live value and verifies, using safe
structured diagnostics and provider/POS interfaces, that Multicard charges the
derived total while AliPOS receives the item subtotal. The AliPOS Desktop bill
and payment status must reconcile with no remaining customer balance before the
rollout is considered complete.

## Failure handling and rollback

If invoice creation, callback validation, AliPOS submission, receipt total, or
POS reconciliation is wrong, immediately set
`INPLACE_ONLINE_PAYMENT_ENABLED=false` and recreate only the backend service.
Already-created invoices remain tracked: valid callbacks continue to be
accepted, and cancellation, expiry, or refund follows the existing safe state
machine. Delivery online payment remains available throughout.

## Success criteria

- Every authenticated table-order customer can select Online.
- The service percentage comes from the table's current AliPOS hall and is not
  hard-coded.
- Multicard charges the exact service-inclusive customer total.
- AliPOS receives the exact in-place item subtotal.
- The POS bill has the service charge exactly once and no unpaid balance after
  successful online payment.
- Delivery payment behavior is unchanged.
- Global table online payment can be disabled immediately through the existing
  backend flag.
