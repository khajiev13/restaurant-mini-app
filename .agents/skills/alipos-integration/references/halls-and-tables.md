# AliPOS halls and tables

Last live verification: 2026-07-13.

## Working request

`GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables`

Resolve the restaurant ID from trusted server configuration or a verified
restaurants response. The response contains:

```text
halls:  id, title, servicePercent
tables: id, title, hallId
```

Join each table to its hall by comparing `table.hallId` with `hall.id`. The live
verification returned one hall and 29 tables, but those counts are tenant data
and must never be hardcoded.

## Backend boundary

Call AliPOS from the backend. A browser-facing API adapter should return only
the fields required by the application and must never expose AliPOS OAuth
credentials or bearer tokens.

## What this proves

- Hall names can be listed.
- Hall service percentages can be returned when present.
- Table names can be listed and grouped by hall.
- A current table ID can be used with `discriminator=inplace` in the verified
  order-create endpoint. See `verified-capabilities.md` for the evidence boundary.

## What this does not prove

- Table occupancy or availability.
- Capacity or party-size rules.
- Date/time slots.
- Booking creation, lookup, update, or cancellation.
- Floor-plan coordinates, geometry, photos, or amenities.

`GET /api/Integration/v1/menu/{restaurantId}/availability` returned `items` and
`modifiers`. It is menu availability, not table occupancy, table availability,
or booking-slot evidence.

## Handling booking requests

No native booking or reservation endpoint is live-verified. Do not guess route
names and do not emit a speculative path, payload, or request code. Before
production implementation, obtain from AliPOS:

- Exact method and versioned path.
- Request and response schemas.
- OAuth authorization scope or tenant feature flag.
- Availability request parameters and timezone rules.
- Booking status and lifecycle semantics.
- Create, lookup, update, cancel, and idempotency behavior.
- Webhook or polling contract.

A vendor contract defines what can be validated. An explicitly approved
separate plan may authorize live validation, but working status still requires
successful saved live evidence in this repository.
