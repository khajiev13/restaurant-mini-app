# Staff Delivery Workflow

Date: 2026-07-07
Status: Draft for review

## Summary

Build a staff delivery mode inside the existing Telegram Mini App. Admins can mark existing Telegram users as staff, and staff users get a simplified delivery workspace where they can take one available delivery order, complete it after delivery, and review their completed deliveries.

The staff UI must stay visually consistent with the current OLOT SOMSA artisan design system and the latest simplified staff prototype: a two-item bottom navigation with `Orders` and `Profile`, plus an `Orders` top segmented control with `Available`, `Active`, and `Completed`.

Delivery completion is local application state for this version. Prior AliPOS probing did not confirm an external endpoint for marking an order delivered, so the backend should be designed with a future AliPOS completion adapter point but must not depend on it.

## Goals

- Let admins identify staff members separately from customers.
- Let staff see unassigned delivery orders that are ready for delivery.
- Let exactly one staff member take an order.
- Let each staff member have at most one active delivery at a time.
- Let only the assigned staff member mark that order delivered.
- Keep staff delivery status simple: assignment is local metadata; delivery completion sets the local order status to `DELIVERED`.
- Keep backend authorization, concurrency control, and validation server-side.
- Keep frontend design consistent with the existing OLOT SOMSA app and the simplified Stitch staff screens.

## Non-Goals

- Batch delivery or multiple stops.
- Route optimization.
- A separate courier app.
- Public registration for staff roles.
- Marking delivery completion in AliPOS unless a confirmed endpoint is added later.
- Missing phone/address/map states. Customer phone, delivery address, items, total, and payment method are already validated before the order enters this workflow.
- Redesigning the customer menu, cart, checkout, or customer order history.

## Current System Context

The app already has:

- Telegram Mini App authentication through validated Telegram `initData`.
- JWT-backed `current_user` lookup by `telegram_id`.
- `users`, `addresses`, and `orders` tables.
- Customer order creation and order status polling.
- AliPOS order IDs and status fields on local orders.
- Existing artisan UI tokens in `frontend/src/artisan.css` and shared layout primitives in `frontend/src/components/artisan/ArtisanLayout.tsx`.

Current gaps:

- `users` has no role field.
- `orders` has no staff assignment fields.
- Staff/admin authorization does not exist.
- Customer order endpoints are scoped to the current customer and cannot serve staff workflows.
- `OrderResponse` does not include denormalized customer/address data needed by staff cards.
- Local order status can drift from AliPOS, so staff take actions should refresh or validate candidate order status before assignment.

## Product Decisions

### Staff Mode

Users with role `staff` should see Staff Mode by default when opening the mini app. Staff Mode has:

```text
Bottom nav:
- Orders
- Profile
```

Inside `Orders`:

```text
Available | Active | Completed
```

The app should not show a bottom `Activity` tab for staff. Active delivery is an `Orders` tab, not a separate app section.

Users with role `customer` continue to see the current customer mini app. Users with role `admin` can access admin functionality and should also be allowed to use staff endpoints if needed, but admin UI is not part of this staff UI spec except for role-management API support.

### One Active Delivery

Each staff member can have only one active delivery at a time. An active delivery is an order with:

```text
assigned_staff_id = current staff telegram_id
delivered_at is null
status is not CANCELLED
status is not DELIVERED
```

If staff already has an active delivery, the `take order` endpoint returns a conflict and the UI sends them to the `Active` tab.

### Available Orders

For MVP, an available delivery order is:

```text
discriminator = delivery
status = TAKEN_BY_COURIER
assigned_staff_id is null
payment is collectible or settled
```

Payment is collectible or settled when:

```text
payment_method = cash
or payment_status = paid
```

This avoids handing staff an unpaid online order. The UI may show preparing or non-ready orders as disabled only if the backend chooses to include them later, but the initial API should return actionable available orders only.

### Delivery Completion

When the assigned staff member marks an order delivered:

```text
status = DELIVERED
delivered_at = current UTC timestamp
```

There is no `delivered_by_staff_id` field. The assigned staff member is the delivery owner, and the backend must enforce that only the assigned staff member can complete the order.

If a future AliPOS endpoint is confirmed, a small adapter can be called after local validation. Until then, `DELIVERED` is local state and should not be overwritten by stale AliPOS polling or webhooks.

## UI Design

### Visual Source Of Truth

Use the latest simplified staff prototype from:

```text
/Users/khajievroma/Downloads/stitch_remix_of_order_status-2.zip
```

Primary references:

- `staff_available_orders_simplified_nav`
- `staff_active_delivery_simplified_nav`
- `staff_delivery_history_simplified_nav`
- `staff_order_detail_pre_take`
- `staff_confirm_delivery_mvp`

Do not copy the generated static HTML. Rebuild the screens as React components using the existing app conventions, shared tokens, and typed API client.

### Design Consistency Rules

- Use OLOT SOMSA terracotta primary color `#a33800`.
- Use the existing `Plus Jakarta Sans` headline and `Manrope` body typography.
- Use the current surface tokens from `frontend/src/artisan.css`.
- Use large touch targets for operational actions.
- Keep staff screens action-first and easy to scan.
- Use a two-item staff bottom nav: `Orders`, `Profile`.
- Use top segmented tabs inside staff orders: `Available`, `Active`, `Completed`.
- Keep CTAs visually consistent with existing gradient primary buttons.
- Do not add decorative marketing sections.
- Do not hide `Take Order`, `Open Map`, `Call Customer`, or `Mark Delivered` below unclear scroll depth.

### Available Tab

The `Available` tab shows unassigned ready delivery orders.

Each order card shows:

- Order number or short order ID fallback.
- Ready status.
- Customer name.
- Delivery address summary.
- Distance if available from existing coordinates; otherwise omit distance.
- Item summary.
- Payment type: `Cash on Delivery` or `Paid Online`.
- Total amount.
- Primary `Take Order` button.

States:

- Loading skeleton.
- Empty state: no available orders.
- Failed state with retry.
- Conflict state after tapping take: order was already taken or no longer available.

### Pre-Take Order Detail

The pre-take detail screen shows:

- Order status.
- Order number.
- Customer name.
- Call customer action.
- Delivery address.
- Open map action.
- Items and quantities.
- Payment method and total.
- Sticky bottom `Take Order` CTA.

The CTA must be visible and consistent across screen sizes. The older prototype that lacked this CTA should not be used.

### Active Tab

The `Active` tab shows the current staff member's active delivery.

It shows:

- Order number.
- Customer name.
- Call customer action.
- Delivery address.
- Open map action.
- Items summary.
- Payment block.
- Primary `Mark Delivered` CTA.

If payment is cash, the payment block must say the exact amount to collect. If payment is online and paid, it should clearly say `Paid Online`.

If there is no active delivery, show a simple empty state and an action to go to `Available`.

### Confirm Delivered Bottom Sheet

When staff taps `Mark Delivered`, show a bottom sheet confirmation.

For cash orders:

- Display `I have collected <amount> cash`.
- Require staff to check the confirmation box before enabling `Confirm & Mark Delivered`.

For paid online orders:

- Do not require a cash checkbox.
- Confirm that the order will be marked delivered.

States:

- Initial confirmation.
- Submitting.
- Success feedback.
- Failure with retry and cancel.

### Completed Tab

The `Completed` tab shows deliveries completed by the current staff member.

Each card shows:

- Order number.
- Delivered time.
- Address district or summary.
- Total amount.
- Payment type.
- Elapsed delivery time if available from `assigned_at` to `delivered_at`.

The heading and tabs must not overlap. The simplified prototype currently has a history header overlap that must be fixed in implementation.

## Backend Design

### Roles

Add a server-owned role field to `users`:

```text
role VARCHAR(32) NOT NULL DEFAULT 'customer'
```

Allowed roles:

```text
customer
staff
admin
```

The frontend must never be trusted for role. Every protected endpoint derives identity and role from the JWT and current database user.

Bootstrap the first admin using a secure deployment setting such as:

```text
BOOTSTRAP_ADMIN_TELEGRAM_IDS=123,456
```

During Telegram auth, if the authenticated `telegram_id` is in the bootstrap set, the backend may promote that user to `admin`. This avoids unauthenticated first-admin creation.

### Order Assignment Fields

Add local delivery assignment fields to `orders`:

```text
assigned_staff_id BIGINT NULL REFERENCES users(telegram_id) ON DELETE SET NULL
assigned_at TIMESTAMP NULL
delivered_at TIMESTAMP NULL
```

Do not add `delivered_by_staff_id`. The assigned staff member is the delivery owner.

Recommended indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_assigned_staff_id ON orders(assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_staff_available
  ON orders(status, assigned_staff_id, discriminator);
```

If the production database is PostgreSQL, add a partial unique index for one active delivery per staff member:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_one_active_delivery_per_staff
  ON orders(assigned_staff_id)
  WHERE assigned_staff_id IS NOT NULL
    AND delivered_at IS NULL
    AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED');
```

The service layer must still check this rule explicitly so API responses can return a helpful `409 Conflict`.

### Service Layer

Create staff/admin service modules so routers stay thin.

Recommended backend units:

- `app/services/permissions.py`: role checks and helpers.
- `app/services/order_status_service.py`: safe local status transitions and AliPOS reconciliation guardrails.
- `app/services/staff_delivery_service.py`: available/active/completed queries, take order, mark delivered.
- `app/services/admin_user_service.py`: user search and role assignment.

Services should raise explicit domain exceptions or FastAPI `HTTPException` consistently. They should not trust request bodies for actor identity.

### Staff Endpoints

All staff endpoints require `role in ('staff', 'admin')`.

```http
GET /api/staff/orders/available
GET /api/staff/orders/active
GET /api/staff/orders/completed
GET /api/staff/orders/{order_id}
POST /api/staff/orders/{order_id}/take
POST /api/staff/orders/{order_id}/delivered
```

The backend derives staff identity from `current_user.telegram_id`.

`POST /take` flow:

1. Require staff/admin role.
2. Reject if current staff already has an active delivery.
3. Load target order with row-level lock.
4. Refresh AliPOS status for the target order if `alipos_order_id` exists.
5. Reject if status is not `TAKEN_BY_COURIER`.
6. Reject if `assigned_staff_id` is already set.
7. Reject if payment is neither cash nor paid.
8. Set `assigned_staff_id = current_user.telegram_id`.
9. Set `assigned_at = now`.
10. Commit and return staff order response.

Conflict responses:

- `409` if staff already has active delivery.
- `409` if order was already taken.
- `409` if order is no longer available.
- `403` if current user is not staff/admin.
- `404` if order does not exist or is not a delivery order.

`POST /delivered` flow:

1. Require staff/admin role.
2. Load target order with row-level lock.
3. Reject if `assigned_staff_id != current_user.telegram_id`.
4. Reject if order is cancelled.
5. Return current state if already delivered.
6. Set `status = DELIVERED`.
7. Set `delivered_at = now`.
8. Set `status_updated_at = now`.
9. Commit and return staff order response.

For MVP, admin users using the staff UI should still follow the same assigned-staff completion rule. Admin override completion is intentionally excluded to keep audit meaning clear.

### Admin Role Endpoints

If the admin dashboard already exists, it should consume backend endpoints rather than writing directly to the database.

All admin endpoints require `role = admin`.

```http
GET /api/admin/users?query=<phone-or-name-or-username>
PATCH /api/admin/users/{telegram_id}/role
```

Role patch request:

```json
{
  "role": "staff"
}
```

Validation rules:

- Only `customer`, `staff`, and `admin` are accepted.
- Admin cannot remove their own final admin role.
- User search returns existing users only. Public invite flow is out of scope.
- Phone numbers are useful for lookup, but `telegram_id` is the durable role key.

### Staff Order Response

Add a staff-specific response model instead of overloading customer `OrderResponse`.

Fields:

```json
{
  "id": "uuid",
  "order_number": "string or null",
  "status": "TAKEN_BY_COURIER",
  "created_at": "iso datetime",
  "status_updated_at": "iso datetime or null",
  "assigned_at": "iso datetime or null",
  "delivered_at": "iso datetime or null",
  "customer": {
    "telegram_id": 123,
    "first_name": "Azizbek",
    "last_name": "R.",
    "phone_number": "+998..."
  },
  "address": {
    "full_address": "string",
    "latitude": "string",
    "longitude": "string",
    "entrance": "string or null",
    "apartment": "string or null",
    "floor": "string or null",
    "courier_instructions": "string or null"
  },
  "items": [],
  "total_amount": 36000,
  "delivery_fee": 0,
  "payment_method": "cash",
  "payment_status": null,
  "assigned_staff": {
    "telegram_id": 123,
    "first_name": "Staff",
    "last_name": "Name"
  }
}
```

Use Pydantic models for these response contracts. Do not expose unrelated payment gateway internals in staff responses.

## Status And Reconciliation

AliPOS remains the source for restaurant-side order preparation status until local staff delivery completion.

Rules:

- `TAKEN_BY_COURIER` means the order is ready for staff assignment in this app.
- Local `DELIVERED` is terminal for this app.
- Local `CANCELLED`/`CANCELED` is terminal for this app.
- Webhook or polling updates must not overwrite local `DELIVERED` with stale AliPOS statuses.
- Before assigning an order, refresh that order's AliPOS status when possible.
- If AliPOS refresh fails during list loading, return cached data with a visible refresh retry.
- If AliPOS refresh fails during `take`, fail closed with a clear retryable error rather than assigning a potentially stale order.

## Security Requirements

- All staff/admin endpoints require JWT auth.
- Role checks happen server-side from the database user row.
- The frontend must not send staff/admin actor fields.
- Staff can only complete orders assigned to their own `telegram_id`.
- Admin role management is admin-only.
- Every order mutation uses a transaction.
- `take` and `delivered` load the order row with `SELECT ... FOR UPDATE` on PostgreSQL.
- Conflict cases return `409`, not silent success.
- Pydantic schemas validate all request and response bodies.
- Logs should include order IDs and actor telegram IDs but not full phone numbers or sensitive payment gateway details.
- Existing customer endpoints remain scoped to `current_user.telegram_id`.

## Frontend Architecture

Add staff UI as a focused module, not as copied static HTML.

Recommended frontend units:

- `frontend/src/components/staff/StaffLayout.tsx`: top bar, two-item bottom nav, shared staff screen shell.
- `frontend/src/components/staff/StaffOrderTabs.tsx`: `Available`, `Active`, `Completed` segmented control.
- `frontend/src/components/staff/StaffOrderCard.tsx`: card for available/completed lists.
- `frontend/src/components/staff/StaffPaymentBlock.tsx`: cash/paid display.
- `frontend/src/components/staff/ConfirmDeliveredSheet.tsx`: bottom sheet confirmation.
- `frontend/src/pages/staff/StaffOrdersPage.tsx`: tabbed staff orders page.
- `frontend/src/pages/staff/StaffOrderDetailPage.tsx`: pre-take detail.
- `frontend/src/services/staffApi.ts`: typed staff API calls, or staff functions inside the existing API service if the project prefers one service file.
- `frontend/src/types/staff.ts`: staff response types if existing `types/api.ts` grows too large.

Role-aware routing:

- Extend `User` type and `/users/me` response with `role`.
- After auth, fetch `/users/me` and route users with `role=staff` to staff orders by default.
- Preserve customer routes for `role=customer`.
- If a staff user manually opens a customer route, redirect to staff orders for MVP.

Route shape:

```text
/staff/orders?tab=available
/staff/orders?tab=active
/staff/orders?tab=completed
/staff/orders/:orderId
```

## Error Handling

Frontend error copy should be operational and brief:

- Order already taken: `This order was already taken by another staff member.`
- Already active: `Finish your active delivery before taking another order.`
- Cancelled/no longer available: `This order is no longer available.`
- Delivery completion failure: `Could not mark the order delivered. Try again.`
- Unauthorized: redirect to the correct customer or login state.

The UI should refresh the relevant tab after conflicts.

## Testing Strategy

Backend tests:

- Customer cannot access staff endpoints.
- Staff can list available orders.
- Available excludes assigned, cancelled, delivered, unpaid-online, and non-delivery orders.
- Staff can take an available order.
- Staff cannot take a second active order.
- Two staff taking the same order results in one success and one conflict.
- Only assigned staff can mark delivered.
- Mark delivered is idempotent for the assigned staff.
- Delivered orders appear in the assigned staff member's completed list.
- Admin can search users and assign staff role.
- Non-admin cannot assign roles.
- Final admin cannot remove their own final admin role.

Frontend tests:

- Staff users route to staff orders after auth.
- Staff bottom nav has only `Orders` and `Profile`.
- Staff orders page renders `Available`, `Active`, `Completed` tabs.
- Available order card shows payment, total, address, and `Take Order`.
- Pre-take detail has a sticky `Take Order` CTA.
- Cash confirmation requires the collected-cash checkbox before enabling confirm.
- Paid online confirmation does not require cash checkbox.
- Conflict responses show the correct message and refresh the list.

Manual visual verification:

- Compare staff screens against the simplified Stitch screenshots.
- Check mobile viewport height where sticky CTAs and bottom nav coexist.
- Verify completed/history heading does not overlap the segmented tabs.
- Verify confirm sheet background uses the two-item staff nav.

## Rollout

1. Add backend fields and role-aware API support.
2. Bootstrap one admin by Telegram ID in the deployment environment.
3. Use the admin dashboard to promote test users to staff.
4. Enable staff routes in the mini app.
5. Test against staging or a controlled production staff account.
6. Monitor logs for role denials, assignment conflicts, and delivery completion failures.

## Out Of Scope For Later Specs

- Telegram group bot dispatch.
- Staff shift management.
- Cash settlement ledger.
- Admin override delivery completion.
- Detailed order event audit trail.
- AliPOS delivery completion adapter after official endpoint confirmation.
