---
name: alipos-integration
description: Use when building, reviewing, testing, or troubleshooting the external AliPOS Integration API, including OAuth, restaurant/menu/payment discovery, delivery orders, order status, halls/tables, dine-in tables, table booking, reservations, POS synchronization, or alipos.uz.
compatibility: Requires server-side HTTPS access for live AliPOS calls. Credentials and tokens must remain outside the skill and browser.
---

# AliPOS Integration

## Overview

Use only capabilities with successful saved live evidence in this repository. A
PDF, code path, `OPTIONS` response, `404` probe, or plausible route name does not
make an operation working.

## Route the task

| Request | Required reference |
|---|---|
| What works, authentication, restaurants, menu, payments, or evidence | `references/verified-capabilities.md` |
| Delivery-order creation, reconciliation, or status | `references/delivery-orders.md` |
| Halls, tables, venue data, booking, reservation, or table availability | `references/halls-and-tables.md` |

Read only the references needed for the request.

## Working operations

| Method | Path |
|---|---|
| POST | `/security/oauth/token` |
| GET | `/restaurants` |
| GET | `/api/Integration/v1/paymentMethod/all` |
| GET | `/api/Integration/v1/menu/{restaurantId}/composition` |
| GET | `/api/Integration/v1/menu/{restaurantId}/availability` |
| GET | `/api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` |
| POST | `/api/Integration/v1/order` |
| GET | `/api/Integration/v1/order/{orderId}` |
| GET | `/api/Integration/v1/order/{orderId}/status` |
| DELETE | `/api/Integration/v1/order/{orderId}` |

This ten-operation matrix is the complete working set. `POST /order` is live-
verified for both `delivery` and `inplace` with a resolved `tableId`. Do not promote another
operation because it appears in application code or vendor documentation.

## Integration rules

- Keep OAuth credentials and bearer tokens on the backend.
- Resolve the restaurant ID from trusted server configuration or a verified
  restaurant response. Before using item, modifier, or payment-method IDs,
  fetch current menu composition and current payment methods and resolve the
  configured selections against those responses.
- Resolve hall, table, order, and other returned identifiers from the relevant
  verified response rather than remembered tenant values.
- Never log credentials, tokens, raw customer data, or complete AliPOS responses.
- Persist a stable local `eatsId` before creating any order.
- Do not automatically retry order creation after a timeout or unknown outcome;
  AliPOS idempotency by `eatsId` is not proven.
- For `inplace`, resolve the table from the current halls-and-tables response and
  send `tableId`; keep each customer's cart and order independent.
- Cancel only after a fresh order read still reports `NEW`. Send one DELETE with
  a non-empty comment and treat a transport failure as an unknown outcome.
- Treat menu availability as item/modifier data only.
- Treat halls-and-tables as a static directory only.
- Label code/PDF-only operations as documented but unverified rather than working.

## Unsupported requests

Do not invent implementation instructions for:

- Native booking or reservation creation, lookup, update, or cancellation.
- Table occupancy, capacity, party-size or time-slot availability, floor-plan
  geometry, photos, or amenities.
- AliPOS order-status or stop-list webhooks.
- An AliPOS mark-delivered operation.

For booking or reservation requests, emit no guessed path, payload, or request
code. Require the vendor-confirmed method and versioned path, schema,
authorization scope, availability/timezone rules, and lifecycle contract before
implementation.

Apply the same evidence-first boundary to every unsupported operation.

## Verification checklist

- Method and path appear in the ten-operation working table.
- Request fields match the relevant reference.
- The restaurant ID comes from trusted server configuration or a verified
  response; item, modifier, and payment IDs come from current prerequisite
  lookups.
- Credentials and AliPOS calls stay server-side.
- User-facing claims do not exceed the response semantics.
- Mutating requests are not retried after uncertain outcomes.
- Unsupported operations are identified, not guessed or implemented.

## Common mistakes

| Mistake | Correct behavior |
|---|---|
| Hardcode a remembered item, modifier, or payment ID | Fetch current composition and payment methods, then resolve the configured selection |
| Treat trusted restaurant configuration as permission to cache every ID | Configuration may select the restaurant; item, modifier, and payment IDs still require current lookups |
| Treat `online-order` as checkout | Use it only as the AliPOS payment classification; checkout belongs to the payment provider |
| Use menu availability for tables | It contains menu items/modifiers, not table state |
| Guess a booking or reservation route | Stop and request the vendor contract |
| Reuse a remembered table ID | Resolve the current table from halls-and-tables, then send its returned `tableId` |
| Cancel without checking state | Read the order first; cancel only while it is still `NEW` and include a non-empty comment |
| Treat a PDF-only or code-only route as verified | Label it documented but unverified |
