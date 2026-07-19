# Table Order Success Confirmation Design

## Goal

Replace unsupported preparation and completion tracking on the customer-facing table-order page with one truthful confirmation: the order was placed successfully.

## Scope

This change applies only to table orders (`discriminator === "inplace"`). Delivery-order status tracking remains unchanged.

## Customer Experience

For a successfully submitted table order, the page will:

- show a success icon and the localized heading "Order placed successfully";
- keep the order number, table and hall, payment information, totals, ordered items, and available actions;
- omit the preparation/ready progress tracker; and
- omit the "updating every 15 seconds" message, because successful table-order progress is no longer presented to the customer.

The following table-order states remain distinct because they are accurate and may require customer action:

- payment pending, failed, expired, or under review;
- submission or AliPOS synchronization failure/uncertainty; and
- cancellation.

Background status polling remains in place so externally changing payment, submission, synchronization, and cancellation states can still be surfaced. Successful progression through restaurant-internal statuses does not alter the confirmation heading.

## Status Presentation

The successful table-order states `NEW`, `PAID_AWAITING_RESTAURANT`, `ACCEPTED_BY_RESTAURANT`, and `READY` all render the same success confirmation.

Existing exceptional-state labels and actions remain the source of truth for `AWAITING_PAYMENT`, `PAYMENT_FAILED`, `PAYMENT_REVIEW`, `SYNC_UNKNOWN`, `SUBMISSION_FAILED`, `CANCELED`, and `CANCELLED`.

Delivery orders continue to use their existing status heading and progress steps.

## Localization

Add a dedicated translation key for "Order placed successfully" in the currently shipped English, Uzbek, and Russian locale files. Existing general status translations remain because delivery and exceptional-state views still use them.

## Implementation Boundaries

The change belongs in `ArtisanOrderStatusPage` and its locale/test files. It does not change backend order states, API contracts, AliPOS synchronization, polling intervals, payment accounting, or staff workflows.

## Verification

Component tests will verify that:

- successful table-order statuses show the localized success confirmation;
- table-order preparation/ready progress labels and the polling message are absent;
- exceptional table-order states still display their real labels and actions; and
- delivery-order tracking remains available.

Run the focused component tests, TypeScript checking, linting, and the frontend build after implementation.
