# AliPOS In-place Order Validation — 2026-07-13

This note records the authorized table-order investigation and the behavior implemented from it. It intentionally omits credentials, bearer tokens, restaurant and table identifiers, customer data, complete payloads, and complete AliPOS responses.

## Sanitized live evidence

| Operation | Sanitized request fact | Observed result |
|---|---|---|
| Discover halls and tables | `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` | `result=OK`; active halls, tables, and hall service percentages were available. |
| Create table order | `POST /api/Integration/v1/order` with `discriminator=inplace`, a live `tableId`, server-priced items, and a resolved cash payment method | `result=OK`; AliPOS returned an order reference. |
| Read order status | `GET /api/Integration/v1/order/{orderId}` | `result=OK`; the new order was readable with status `NEW`. |
| Cancel new order | `DELETE /api/Integration/v1/order/{orderId}` with JSON body `{ "comment": "Mijoz yangi buyurtmani bekor qildi" }` | `result=OK` during the authorized test; cancellation requires a non-empty comment and is used only after a fresh status read confirms `NEW`. |

The cancellation response is deliberately discarded by the integration adapter. An exploratory response contained a company-scoped token field that must never be logged, persisted, or returned to a customer.

## Implemented safety rules

- Customer requests never provide a trusted AliPOS table ID, price, service charge, payment ID, or total.
- A signed Telegram QR entry or six-character manual code resolves against the current AliPOS hall/table directory and produces a short-lived table access token.
- Cash orders are submitted once to AliPOS. A timeout or transport failure after `POST /order` becomes `SYNC_UNKNOWN`; the create request is not automatically retried.
- Customer checkout uses a client-generated request UUID with a unique per-user database constraint. A browser retry returns the original order instead of creating a second AliPOS order or Multicard invoice.
- Online orders remain local until Multicard verifies store, signature, invoice ID, and exact amount. The paid order is then submitted with AliPOS's `online-order` payment classification.
- Invalid Multicard callbacks return non-2xx; only a valid or already-processed callback receives the documented empty `{}` acknowledgement.
- Switching an unpaid order to cash holds a database row lock and requires Multicard to confirm invoice cancellation before AliPOS submission.
- Definite invoice failures and confirmed expiries can retry online or switch to cash. Network-ambiguous invoice creation enters a verification state and is not retried automatically.
- Cancelling an unpaid online order uses the same confirmed invoice-cancellation rule.
- Synced table orders are cancelled only after a live AliPOS status read still returns `NEW`.
- Paid cancellation calls AliPOS first and durably queues a full Multicard refund. Unknown refund outcomes remain pending and are reconciled with `GET /payment/{uuid}` rather than repeating `DELETE`.
- AliPOS order-status webhooks update tracking. Stop-list webhooks are merged with the live AliPOS item/modifier availability endpoint, and checkout re-prices and re-validates the cart on the server.
- Customer order APIs omit AliPOS order/eats IDs, raw table/hall IDs, and raw provider errors. An authenticated restore endpoint can issue a fresh signed table context after a payment-return WebView opens without session storage, but its token is capped to the original table-access expiry persisted on that order.

## QR operations

`GET /api/tables/manifest` requires an admin JWT and returns only printable fields: table and hall titles, service percentage, manual code, Telegram start parameter, and deep link. Print the `deep_link` as the QR and the `manual_code` beside it.

Required deployment configuration:

```env
TELEGRAM_BOT_USERNAME=olotsomsa_zakaz_bot
TABLE_ACCESS_SECRET=<independent random secret>
TABLE_ACCESS_TTL_SECONDS=28800
ALIPOS_RESTAURANT_ID=<restaurant UUID>
```

Apply `database/migrations/2026-07-13-qr-table-ordering.sql` before starting the new backend against an existing database.

Customer recovery endpoints:

- `POST /api/orders/{orderId}/retry-payment`
- `POST /api/orders/{orderId}/switch-to-cash`
- `POST /api/tables/restore/{orderId}`

## Current limits

- This implementation does not add reservations, table occupancy, floor plans, waiter calls, shared carts, shared bills, split payments, order merging, or table transfer.
- QR artwork/export is an operator step based on the manifest; there is no admin print designer in this change.
- Production deployment and physical QR placement are intentionally outside this implementation pass.
