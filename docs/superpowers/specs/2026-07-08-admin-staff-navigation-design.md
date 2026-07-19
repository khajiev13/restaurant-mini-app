# Admin Staff Navigation

Date: 2026-07-08
Status: Approved for implementation planning

## Summary

Admins are a superset role. They can manage user roles and can also help with deliveries. The current Phase 1 staff delivery implementation already allows admins to call staff delivery APIs, but the frontend sends admins directly into the staff delivery UI and gives them only the two staff tabs: `Orders` and `Profile`.

The follow-up change should make admin mode explicit:

```text
Admin bottom nav:
- Admin
- Orders
- Profile
```

Staff users keep the simpler two-tab shell:

```text
Staff bottom nav:
- Orders
- Profile
```

## Goals

- Make the admin dashboard the default landing place for `role = admin`.
- Let admins switch into delivery work from the same mini app.
- Reuse the existing staff delivery UI for admin deliveries.
- Preserve the existing staff delivery rules for admins: one active delivery at a time, assigned staff identity comes from the current Telegram user, and only the assigned user can mark delivered.
- Keep role management admin-only.
- Keep visual language consistent with the current OLOT SOMSA staff/customer design.

## Non-Goals

- A separate admin-only app.
- Admin override delivery completion for orders assigned to other staff.
- Batch delivery, routing, or delivery reassignment.
- Changing the backend role enum.
- Changing customer navigation.

## Roles

### Customer

Customers continue to see the existing customer app:

```text
Menu | Orders | Cart | Profile
```

Customer users cannot access admin or staff routes.

### Staff

Staff users continue to see the delivery app:

```text
Orders | Profile
```

Staff users default to `/staff/orders` after login.

### Admin

Admin users default to `/admin` after login and see:

```text
Admin | Orders | Profile
```

The `Admin` tab is for role management. The `Orders` tab is the existing staff delivery workflow. The `Profile` tab is the existing staff/admin profile view with logout.

## Routing

Add admin routes:

```text
/admin
/admin/users
```

For Phase 1.1, `/admin` can be the role-management dashboard directly. `/admin/users` can either alias to the same screen or be reserved if the implementation wants a separate route.

Role-sensitive routing should become explicit:

```text
customer -> customer routes
staff    -> /staff/orders by default
admin    -> /admin by default
```

Suggested route behavior:

- `/` for admin redirects to `/admin`.
- `/staff/orders` remains accessible to admin.
- `/staff/orders/:orderId` remains accessible to admin.
- `/profile` renders the staff/admin profile shell for both `staff` and `admin`.
- `/admin` is accessible only to admin.
- Customer and staff users opening `/admin` redirect to their default app.

## Admin Dashboard

The admin dashboard should consume the existing admin APIs:

```text
GET /api/admin/users?query=<phone-or-name-or-username>
PATCH /api/admin/users/{telegram_id}/role
```

The first version should include:

- Search input for phone, name, or username.
- User result rows with name, username, phone, Telegram ID, and current role.
- Role selector with `customer`, `staff`, and `admin`.
- Save/update action per user.
- Loading, empty, and error states.
- Protection messages surfaced from the backend, especially final-admin demotion protection.

No frontend should send actor identity. The backend continues to derive admin identity from the JWT.

## Navigation Shell

Create a role-aware staff/admin layout rather than duplicating the whole staff shell.

For staff:

```text
Orders | Profile
```

For admin:

```text
Admin | Orders | Profile
```

The shell should keep the existing top bar, OLOT SOMSA logo, spacing, colors, and bottom-nav styling. The three-item admin nav can use the same nav item component with a three-column grid.

Suggested icons:

- `Admin`: `admin_panel_settings`
- `Orders`: `receipt_long`
- `Profile`: `person`

## Backend Behavior

No schema change is needed.

Keep:

- Staff delivery endpoints require `role in ('staff', 'admin')`.
- Admin role-management endpoints require `role = admin`.
- Delivery assignment uses `assigned_staff_id = current_user.telegram_id`, even when the current user is admin.
- Admins follow the same one-active-delivery and assigned-user completion rules as staff.

## Error Handling

Admin dashboard should surface backend errors directly when they are safe and user-actionable:

- Invalid role.
- User not found.
- Cannot remove the final admin role.
- Generic network/server failure.

Staff delivery error handling stays as implemented.

## Testing

Add focused frontend tests:

- Admin users landing on `/` route to `/admin`.
- Admin users can open `/staff/orders`.
- Admin users see `Admin`, `Orders`, and `Profile` nav items.
- Staff users still see only `Orders` and `Profile`.
- Customers cannot access `/admin`.
- Admin dashboard searches users and updates roles through the existing API service functions.
- Final-admin demotion errors render clearly.

Backend tests already cover admin APIs and staff delivery permissions. Add backend tests only if the implementation changes those permission helpers.

## Deployment Notes

This is a frontend-focused follow-up on top of the existing Phase 1 migration and admin APIs. Deploying it should not require a new database migration.
