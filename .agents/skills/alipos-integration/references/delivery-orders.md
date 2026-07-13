# AliPOS delivery orders

## Authentication

Call `POST /security/oauth/token` from the backend with form-encoded
`client_id`, `client_secret`, and `grant_type=client_credentials`. Send the
returned token as `Authorization: Bearer <token>` with
`Accept: application/json`. Keep credentials and tokens outside browser code,
logs, and persisted order data.

## Prerequisites

1. Authenticate server-side.
2. Resolve the restaurant from trusted server configuration or a verified
   restaurants response.
3. Fetch current menu composition and use only item/modifier IDs resolved from
   that response.
4. Fetch current payment methods and resolve the configured payment
   classification against that response.
5. Persist a stable unique local `eatsId` before sending the order.

A trusted server configuration may supply the restaurant ID. It does not make
remembered item, modifier, or payment IDs safe: those require the current
menu-composition and payment-method lookups above. Never put AliPOS credentials
in frontend code.

## Create delivery order

`POST /api/Integration/v1/order`

Use this complete live-proven field structure with placeholders only:

```json
{
  "discriminator": "delivery",
  "platform": "<2-20 character source>",
  "eatsId": "<stable local order reference>",
  "restaurantId": "<configured restaurant id>",
  "comment": "",
  "deliveryInfo": {
    "clientName": "<customer name>",
    "phoneNumber": "<customer phone>",
    "deliveryAddress": {
      "full": "<full address>",
      "latitude": "<latitude>",
      "longitude": "<longitude>"
    }
  },
  "paymentInfo": {
    "paymentId": "<resolved payment method id>",
    "itemsCost": 0,
    "total": 0,
    "deliveryFee": 0
  },
  "items": [
    {
      "id": "<resolved menu item id>",
      "quantity": 1,
      "price": 0,
      "modifications": []
    }
  ]
}
```

Replace the zero amount examples with prices and totals from current menu data
and trusted server calculations. Validate client-submitted selections and never
trust client-submitted totals. The proven example used an empty `modifications`
array; do not invent a modifier-object payload. Any modifier IDs used by a
separately verified shape must still come from current menu composition.

Successful live responses contained:

```json
{
  "result": "OK",
  "orderId": "<AliPOS order id>"
}
```

Persist the returned order ID with the local order only after confirmed success.

## Unknown outcomes

Do not automatically retry the POST after timeout, connection loss, or another
unknown outcome. AliPOS idempotency behavior for `eatsId` has not been proven.
Preserve the same local `eatsId`, mark the synchronization outcome unknown, and
reconcile operationally before another mutation is authorized. Do not invent an
idempotency key, an `eatsId` lookup endpoint, or an external-reference
reconciliation route.

## Full order read

`GET /api/Integration/v1/order/{orderId}` returns the detailed order, including
delivery, payment, items, status, and order number. Use it for reconciliation
and detailed display when the AliPOS order ID is known.

## Compact status read

`GET /api/Integration/v1/order/{orderId}/status` returns `comment`, `status`, and
`updatedAt`. Use it for lightweight polling. The live runs observed `NEW`
followed by `ACCEPTED_BY_RESTAURANT`; status changes are asynchronous and those
values are not an exhaustive enum.

## Payment behavior

- Cash and `online-order` were accepted in successful live creates.
- Fetch current payment methods from
  `GET /api/Integration/v1/paymentMethod/all`, then resolve the configured
  classification against that response before each ID is used.
- `online-order` is an AliPOS payment classification. It does not create a
  payment link, QR code, redirect, deep link, callback, or payment status.
- Use a separate payment-provider integration, such as Multicard, when customer
  checkout, wallet redirects, callbacks, or payment status are required.

## Not available as verified instructions

- AliPOS mark-delivered.
- Order-status or stop-list webhook setup.

The vendor PDF is not enough to promote these remaining operations. In-place
creation and cancellation of a freshly verified `NEW` order now have separate
saved live evidence; follow `verified-capabilities.md` and
`halls-and-tables.md` for those boundaries.
