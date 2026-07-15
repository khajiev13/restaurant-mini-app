# Admin and Staff Table Inspection Design

**Date:** 2026-07-15

**Status:** Approved in conversation; pending written-spec review

## Summary

Add a read-only Tables workspace for staff and admins. It lists every table in
the current AliPOS hall/table directory and overlays only active table orders
created through this mini app. Staff can inspect a combined table-level item
and total summary, open the original customer orders, and browse the same live
menu catalog customers see.

The workspace must never claim that a table is free, occupied, available, or
reserved. The verified AliPOS integration exposes a static table directory and
individual known-order reads; it does not expose table occupancy or all open
POS bills. Orders entered directly by restaurant staff in AliPOS are therefore
outside this feature.

Version one is inspection-only. It does not let staff create, edit, accept,
cancel, transfer, pay, merge, or otherwise mutate a table order.

## Confirmed product decisions

- Both `staff` and `admin` roles can use the workspace.
- Every current AliPOS table is displayed, including tables with no mini-app
  order.
- Order data covers mini-app-created `inplace` orders only.
- The menu is browse-only and retains current customer prices, images,
  categories, descriptions, and availability.
- Multiple customer orders at one table remain separate records, while the UI
  presents an aggregate table summary first.
- Only current active orders are shown. Completed and cancelled orders are not
  history in this workspace.
- The selected navigation approach is one `Tables` destination with an
  internal `Tables | Menu` toggle.

## Goals

- Give staff and admins one operational view of all restaurant tables.
- Make mini-app table activity and ordered items visible without opening
  customer accounts.
- Show a safe combined quantity and payable-total summary per table while
  preserving the original order boundaries.
- Reuse the customer menu presentation without exposing customer cart or
  checkout behavior to staff roles.
- Keep order status reasonably fresh using only verified AliPOS reads.
- Degrade visibly and safely when the table directory or order status cannot
  be refreshed.

## Non-goals

- AliPOS-native or waiter-entered orders that did not originate in this app.
- Table occupancy, availability, capacity, party size, booking, reservations,
  floor-plan geometry, or physical table management.
- Staff-side order entry, item editing, order acceptance, cancellation,
  payment handling, table transfer, split bills, shared carts, or merged bills.
- Completed/cancelled table-order history.
- Per-item preparation or served state; order items remain order snapshots.
- Reliance on an AliPOS status webhook, because that webhook is not
  live-verified.
- Any change to customer pricing, service-charge calculation, table payment
  gates, refunds, or AliPOS create semantics.

## Evidence boundary

The design uses only these verified AliPOS capabilities:

- `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` for the
  current hall and table directory.
- `GET /api/Integration/v1/order/{orderId}` or the existing verified
  per-order status read for known app-created orders.
- Existing menu composition and availability reads behind `GET /api/menu`.

The hall/table response proves titles, relationships, and hall service
percentages. It does not prove occupancy. The UI must use phrases such as
`2 mini-app orders` and `No mini-app orders`, never `Occupied`, `Free`, or
`Available`.

OAuth credentials, bearer tokens, raw provider responses, and customer payment
identifiers remain backend-only. AliPOS identifiers may be used as internal API
keys but are never rendered as user-facing text.

## Roles, routing, and navigation

### Staff

Staff default routing remains `/staff/orders`. Their bottom navigation becomes:

```text
Tables | Delivery | Profile
```

`Delivery` points to the existing `/staff/orders` workflow; only its displayed
label changes from the ambiguous `Orders` label.

### Admin

Admin default routing remains `/admin`. Their bottom navigation becomes:

```text
Admin | Tables | Delivery | Profile
```

Admins use the same Tables and delivery pages as staff. Role management stays
admin-only.

### Routes

```text
/staff/tables                 all-table workspace
/staff/tables?view=menu       browse-only menu within the workspace
/staff/tables/:tableId        one table's combined and original-order detail
```

The route guard accepts `staff` and `admin` and redirects customers to their
customer home. Backend authorization is authoritative and uses the current
database user resolved from the JWT; the client never supplies an acting staff
identity.

## User experience

### Tables overview

The page uses the existing OLOT SOMSA staff shell and the approved internal
toggle:

```text
Tables | Menu
```

The Tables view contains:

- A title and last-refresh indicator.
- Filters for `All`, `With orders`, and `Attention`.
- Natural table-name sorting within each hall.
- Hall headings with the current service percentage when supplied.
- A neutral card for every table.
- Terracotta emphasis, plus explicit text, for tables with synchronized
  mini-app orders. Color is never the only signal.

A table card shows:

- Table title.
- Active synchronized mini-app order count.
- A short combined item summary.
- Combined payable total when at least one synchronized order exists.
- Separate `Processing` or `Needs attention` counts when applicable.

Tables with no synchronized, processing, or attention records show
`No mini-app orders`. This statement does not imply that the physical table is
empty or that AliPOS has no native bill for it.

### Table detail

Selecting a table opens a dedicated detail route. It shows:

1. Table title, hall title, and current hall service percentage, or the saved
   hall snapshot when the table is no longer listed.
2. Data-freshness state.
3. Combined synchronized-order count, item count, and payable total.
4. Combined item lines.
5. Original mini-app orders with order number, creation time, status, payment
   classification, item lines, and persisted totals.
6. Separate processing and attention records that are excluded from the
   combined synchronized totals.

The combined item key is the persisted product ID, persisted unit price, and a
normalized modifier signature containing modifier IDs, quantities, and prices.
Lines with different modifiers or prices are not merged merely because their
names match. Quantities are summed only for identical keys.

Combined money values are sums of persisted server-authoritative order values:

- `items_cost` is the sum of qualifying orders' persisted `items_cost`.
- Service amount is the sum of each qualifying order's
  `total_amount - items_cost - delivery_fee`.
- Payable total is the sum of qualifying orders' persisted `total_amount`.

The feature does not reprice old items using the current menu or recompute old
orders using the current hall service percentage.

### Browse-only menu

The Menu view reuses the customer category rail, product cards, images,
descriptions, prices, sold-out state, loading state, and retry behavior. It
adds a persistent `Browse only` explanation and removes:

- Add/remove quantity controls.
- Cart state and sticky cart action.
- Table context entry.
- Checkout navigation.
- Any order-submission action.

Refactor the current private menu-page presentation into focused reusable
components. The customer page uses interactive mode; the staff workspace uses
browse mode. Browse mode must not subscribe to or mutate `useCartStore`.

## Backend architecture

### Service boundary

Create a focused staff table-workspace service. It owns:

- Staff/admin authorization.
- Current directory retrieval and stale-directory fallback.
- Active local table-order selection.
- Throttled status reconciliation for known AliPOS orders.
- Classification into synchronized, processing, and attention groups.
- Table/order aggregation and response construction.

The existing delivery service remains delivery-only. Table inspection must not
weaken its assignee, one-active-delivery, or completion rules.

### Read endpoints

Add staff/admin-authorized endpoints:

```text
GET /api/staff/tables
GET /api/staff/tables/{table_id}
```

The overview returns every directory table with counts, compact combined item
lines, totals, freshness metadata, and state flags. The detail endpoint returns
the complete combined item set and original qualifying orders for one table.
Both endpoints use the same service and classification rules.

The existing `GET /api/menu` remains the menu source. No staff menu mutation
endpoint is added.

### Order classification

Start from local orders satisfying:

```text
discriminator = inplace
status not in DELIVERED, CANCELLED, CANCELED
```

Then classify them as follows:

- **Synchronized:** `alipos_sync_status = synced` and, for online payment,
  `payment_status = paid`. These orders contribute to active counts, combined
  items, and combined totals.
- **Processing:** `alipos_sync_status` is `queued` or `sending`, and the payment
  condition above is satisfied. They are visible but excluded from synchronized
  aggregates until AliPOS acceptance is known.
- **Attention:** `alipos_sync_status` is `failed` or `unknown`. They are visible
  with explicit `Not synchronized` or `Verify in POS` copy and are excluded from
  synchronized aggregates.
- **Excluded pre-order payment states:** `awaiting_payment`, `AWAITING_PAYMENT`,
  `PAYMENT_FAILED`, and `PAYMENT_REVIEW`. These do not represent a restaurant
  order and do not appear in the Tables workspace.
- **Excluded terminal states:** delivered and either cancellation spelling.

Attention records remain visible until another existing reconciliation or
operational process changes their persisted local state. Version one surfaces
but does not resolve them. An unresolved attention record is treated as current
operational risk rather than completed-order history.

### Directory join and removed tables

Use the current five-minute AliPOS directory cache as the fresh source. Extend
it to retain the last successful directory as a stale in-process fallback.

- A fresh directory produces `directory_stale = false`.
- If refresh fails but a prior value exists, return the prior directory with
  `directory_stale = true` and its last-success timestamp.
- If the process has no current or prior directory, return a retryable service
  error. Do not claim that a partial local list represents every table.
- If an active local order references a table absent from the directory, retain
  it under an `Unlisted tables` group using the persisted table/hall snapshots
  and mark `is_listed = false`.

### Status freshness and throttling

Do not rely on customers keeping an order-status page open and do not rely on
the unverified webhook. Reconcile only known app-created AliPOS order IDs through
the verified per-order read.

Add nullable order timestamps:

```text
alipos_status_check_attempted_at
alipos_status_checked_at
```

`attempted_at` is written for every provider-read attempt; `checked_at` is
written only after a successful provider response. This distinction supports
durable throttling and honest stale-data warnings.

For each workspace request:

1. Atomically claim eligible synchronized, non-terminal orders whose last
   attempt is at least 30 seconds old by advancing `attempted_at` in a short
   transaction.
2. Read only those known AliPOS orders with a maximum concurrency of five.
3. Apply successful provider status/order-number updates through the existing
   normalization service and set `checked_at`.
4. Leave cached status unchanged on a provider error.
5. Re-query and aggregate after reconciliation so newly terminal orders no
   longer appear.

The frontend polls the workspace every 15 seconds while the page is mounted and
visible. The durable 30-second server throttle ensures that every client poll
does not become an AliPOS request. A manual refresh makes a new workspace
request but does not bypass the server throttle.

Return `order_status_stale = true` when any displayed synchronized order lacks
a successful status read in the previous 60 seconds or when its latest attempt
is newer than its latest success. Partial provider failure returns cached data
with the stale flag instead of failing the complete workspace.

### Database changes

Add the two nullable status-check timestamps to the ORM model, initialization
schema, and an idempotent migration. No backfill is required; existing null
values cause the first eligible workspace request to refresh those orders.

Add a focused partial index for the table-workspace query, covering table ID,
sync state, status, and status-attempt time for `discriminator = 'inplace'`.
Keep the existing table ID index.

## API response principles

Responses include only what the two staff screens require:

- Generated-at and last-success timestamps.
- Directory and order-status stale flags.
- Hall title and current service percentage.
- Internal hall/table keys, table title, and `is_listed`.
- Synchronized, processing, and attention counts.
- Combined item lines and persisted monetary totals.
- Original order number, timestamps, safe status/payment classifications,
  item snapshots, and persisted totals on the detail endpoint.

Do not return customer Telegram IDs, phone numbers, names, addresses, access
tokens, provider request/response bodies, OAuth data, Multicard identifiers, or
checkout URLs. The workspace's purpose does not require that personal data.

## Frontend component boundaries

Add focused units rather than extending the existing large pages further:

- `StaffTablesPage`: route-level workspace state, polling, toggle, filters, and
  overview rendering.
- `StaffTableDetailPage`: direct-route loading and detail rendering.
- `TableWorkspaceToggle`: accessible `Tables | Menu` selection.
- `TableHallSection`, `TableInspectionCard`, and `TableOrderSummary`: pure
  presentation components.
- `MenuCatalog`: reusable customer/staff catalog presentation with explicit
  interactive or browse mode.
- A staff-tables API module and dedicated response types.

The route-level page owns requests and timers. Presentation components receive
data and callbacks and do not call APIs directly. The polling timer stops on
unmount and while the document is hidden, then refreshes when visibility
returns.

Update `StaffLayout` without duplicating the shell. Staff uses a three-column
bottom navigation; admin uses four columns. Existing customer navigation is
unchanged.

## UI states and error handling

### Tables

- **Loading:** hall and table-card skeletons.
- **Loaded, no mini-app activity:** all current tables remain visible with
  `No mini-app orders`.
- **Empty directory:** explain that AliPOS returned no tables and offer retry.
- **No directory and no cache:** blocking retry state; do not render a local
  subset as the complete directory.
- **Stale directory:** keep cached tables visible with a directory warning and
  last-success time.
- **Partial status failure:** keep cached order data visible with a status
  warning and last-success time.
- **Attention:** explicit text and icon; never imply provider acceptance.
- **Removed table:** display under `Unlisted tables` with an explanatory label.
- **Unauthorized:** backend 403 plus role-aware frontend redirect.

### Menu

Reuse existing loading, loaded, sold-out, empty, and manual-retry behavior. A
menu failure must not remove the Tables view; the user can switch back.

### Accessibility and localization

- Provide Uzbek, Russian, and English strings for every new label and state.
- Use semantic buttons/links, visible focus, and at least 44-by-44-pixel targets.
- Use text and icons in addition to color for all state distinctions.
- Announce refresh failures and recovered freshness through a polite live
  region without announcing every successful poll.
- Preserve Telegram safe-area behavior, large-text support, and layouts at
  320, 375, and 430 pixels.
- Keep natural table sorting and long hall/table title wrapping.

## Testing

### Backend

Add focused tests proving:

- Customers are denied and both staff and admins are authorized.
- The overview contains every current directory table.
- Multiple synchronized orders on one table aggregate correctly while original
  orders remain separate.
- Product lines merge only when product, price, and normalized modifiers match.
- Persisted totals are summed without current-menu repricing.
- Terminal and pre-payment orders are excluded.
- Queued/sending and failed/unknown records are classified and excluded from
  synchronized totals.
- Status reads are limited to known stale order IDs, atomically throttled for
  30 seconds, and bounded to five concurrent calls.
- Successful reads update status/check time; failures retain cached state and
  set stale response metadata.
- A newly terminal provider result disappears from the response.
- Fresh, stale-cache, no-cache failure, empty-directory, and removed-table
  directory paths behave as specified.
- Responses omit customer and provider-sensitive data.
- Delivery staff queries and permissions remain unchanged.

### Frontend

Add focused tests proving:

- Staff and admin navigation contains Tables with the correct item count and
  customer navigation is unchanged.
- Customers cannot open staff table routes.
- Tables/Menu state is represented by the route/query string and survives
  direct loading.
- Hall grouping, natural sorting, filters, neutral empty cards, synchronized
  aggregates, processing, attention, and unlisted groups render correctly.
- Table detail shows the combined summary before original orders.
- Browse-only menu renders live customer catalog information without add/remove,
  cart, checkout, or table-context controls.
- Customer menu behavior remains interactive after component extraction.
- Loading, empty, blocking error, stale directory, partial status error, menu
  error, and retry states render correctly.
- Polling starts, stops on unmount/hidden visibility, resumes on visibility,
  and does not create duplicate timers.
- New copy resolves in Uzbek, Russian, and English.

### Full verification

Before completion, run:

- Complete backend pytest suite.
- Complete frontend Vitest suite.
- Frontend type checking and linting.
- Frontend production build.
- Migration static/idempotency checks.

## Deployment and rollback

Deploy the additive database migration before the backend and frontend images.
The new timestamp columns are nullable and require no backfill. Verify staff and
admin authorization, directory retrieval, one synchronized table-order
aggregate, stale-state behavior, and the browse-only menu after deployment.

Rollback removes the new navigation/routes and endpoints. The additive nullable
columns and partial index may remain safely until a later maintenance window.
This feature never enables online table payment or alters existing order,
payment, refund, or delivery behavior.

## Success criteria

The feature is successful when a staff or admin user can open Tables, see every
current directory table, immediately identify and inspect synchronized
mini-app-created active orders per table, distinguish processing or uncertain
orders without treating them as accepted, and browse the current menu without
any mutation capability. The same screen must remain honest about stale data
and about its inability to see POS-only table activity.
