# Verified AliPOS capabilities

Last live verification: 2026-07-13.

## Evidence standard

Working means a successful saved live execution in this repository for that
method and path family. The vendor PDF may clarify a verified schema but cannot
independently promote an operation. Code presence, `OPTIONS`, speculative route
probing, and `404` responses are not positive evidence.

## Authentication

`POST /security/oauth/token` uses form-encoded `client_id`, `client_secret`, and
`grant_type=client_credentials`. Successful responses contain an access token.
Send it as `Authorization: Bearer <token>` with `Accept: application/json` from
the backend only. Cache it according to its expiry without logging it.

## Verified matrix

| Capability | Method and path | Safe response shape | Evidence |
|---|---|---|---|
| OAuth | `POST /security/oauth/token` | `access_token`, token metadata | Successful live authentication with official credentials |
| Restaurants | `GET /restaurants` | `places[]`: `id`, `title`, `address` | Live 200 |
| Payment methods | `GET /api/Integration/v1/paymentMethod/all` | Array: `id`, `title`, `isExternallyFiscalized` | Live 200 |
| Menu composition | `GET /api/Integration/v1/menu/{restaurantId}/composition` | `categories`, `items`, `lastChange`, `schedules` | Live 200 |
| Menu availability | `GET /api/Integration/v1/menu/{restaurantId}/availability` | `items[]`, `modifiers[]`; both empty in the observed run | Live 200 |
| Halls and tables | `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` | `halls[]`, `tables[]` | Live 200 |
| Create delivery or in-place order | `POST /api/Integration/v1/order` | `result`, `orderId` | Successful live delivery orders and one authorized `inplace` order with a resolved `tableId` |
| Full order | `GET /api/Integration/v1/order/{orderId}` | Delivery, payment, items, status, order number | Multiple live 200 readbacks |
| Compact status | `GET /api/Integration/v1/order/{orderId}/status` | `comment`, `status`, `updatedAt` | Two live 200 responses |
| Cancel new order | `DELETE /api/Integration/v1/order/{orderId}` | Successful response is discarded because it may contain company-scoped fields | Authorized live cancellation after a fresh read confirmed `NEW`; non-empty comment required |

The matrix above contains exactly the ten method/path families verified as
working. No other AliPOS operation belongs in the working set without new saved
positive live evidence.

## Identifier sources

- The restaurant ID may come from trusted server configuration. It may also be
  selected from a verified `GET /restaurants` response.
- Before using an item or modifier ID, fetch current menu composition and match
  the configured selection against the returned data.
- Before using a payment-method ID, fetch current payment methods and match the
  configured payment classification against that response. Do not treat a
  stored legacy ID as current evidence.
- Resolve hall, table, and order IDs from their verified responses rather than
  copying observed tenant values into code or documentation.

## Observed semantics

- Payment methods included cash, card, corporate card, and `online-order`;
  resolve the chosen ID from the current response.
- `online-order` was accepted by AliPOS but did not return a payment link, QR
  code, redirect, or deep link.
- Menu availability is not table availability.
- One observed venue response contained one hall and 29 tables; counts are
  tenant data, not constants.
- Observed order statuses included `NEW` and `ACCEPTED_BY_RESTAURANT`; do not
  treat this as an exhaustive enum.
- In-place creation accepted `discriminator=inplace` with a `tableId` resolved
  from the current halls-and-tables response.
- Cancellation was accepted for a freshly verified `NEW` order with a non-empty
  comment. This does not prove cancellation for later statuses.

## Not verified as working

- Order-status and stop-list webhooks.
- AliPOS delivery completion.
- Native booking/reservation creation, lookup, update, or cancellation.
- Table occupancy, capacity, party-size or time-slot availability, or floor
  geometry.

These remain outside implementation guidance even when code or the vendor PDF
mentions them.

## Repository evidence

- `notebooks/alipos_support_report_ru_uz.ipynb`
- `notebooks/alipos_table_booking_discovery.ipynb`
- `docs/alipos/alipos-integration-api-2026-07-08.pdf`
- `backend/app/services/alipos_api.py`
- `backend/app/routers/orders.py`
- `docs/alipos/inplace-order-validation-2026-07-13.md`
