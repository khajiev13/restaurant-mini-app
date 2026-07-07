# Staff Delivery Phase 1 Rollout

Date: 2026-07-07

## What This Enables

Phase 1 adds role-aware staff delivery inside the Telegram Mini App:

- Admins can promote existing users to `staff` or `admin`.
- Staff users see a staff order workspace instead of the customer tabs.
- Staff can take one available delivery order at a time.
- Staff can mark their own active delivery as delivered.
- Delivered completion is local app state. AliPOS delivery-completion writeback is intentionally not required for this phase.

## Deployment Inputs

Set the bootstrap admin Telegram ID before first admin setup:

```sh
BOOTSTRAP_ADMIN_TELEGRAM_IDS=<admin-telegram-id>
```

This is a bootstrap escape hatch only. After a durable admin exists, keep the admin role in the database and avoid leaving broad bootstrap IDs configured longer than necessary.

## Database Migration

Apply the additive migration:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/2026-07-07-staff-delivery-phase-1.sql
```

For the deployed `restaurant` host, where Docker runs inside WSL:

```sh
cat database/migrations/2026-07-07-staff-delivery-phase-1.sql | ssh restaurant 'wsl docker exec -i restaurant_postgres sh -lc '\''psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'\'''
```

If already inside the WSL shell on the server, run:

```sh
docker exec -i restaurant_postgres sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/2026-07-07-staff-delivery-phase-1.sql
```

## Smoke Test

1. Log in as the configured bootstrap admin in the Telegram Mini App.
2. Open the admin dashboard, or call the admin role API if the dashboard is deployed separately.
3. Promote one test user to `staff`.
4. Log in as that staff user in the Telegram Mini App.
5. Confirm staff mode shows only the two bottom tabs: `Orders` and `Profile`.
6. Confirm available orders are delivery orders in `TAKEN_BY_COURIER`, unassigned, and either cash or already paid.
7. Take one available order.
8. Confirm the order moves to `Active`.
9. Confirm trying to take another order shows the active-delivery conflict.
10. Mark the active delivery as delivered.
11. Confirm the order appears in `Completed` with delivered time and delivery duration.
12. Confirm the normal customer app still loads for a customer user.
13. Confirm AliPOS polling/webhook refreshes do not overwrite local `DELIVERED` orders back to non-terminal statuses.

## Rollback Notes

The migration is additive, so rolling the app back to a previous image should not require dropping the new columns immediately.

Only remove the schema additions if every role-aware build has been rolled back and no staff/admin data needs to be preserved:

```sql
DROP INDEX IF EXISTS uq_orders_one_active_delivery_per_staff;
DROP INDEX IF EXISTS idx_orders_staff_available;
DROP INDEX IF EXISTS idx_orders_delivered_at;
DROP INDEX IF EXISTS idx_orders_assigned_staff_id;
ALTER TABLE orders DROP COLUMN IF EXISTS delivered_at;
ALTER TABLE orders DROP COLUMN IF EXISTS assigned_at;
ALTER TABLE orders DROP COLUMN IF EXISTS assigned_staff_id;
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_valid;
ALTER TABLE users DROP COLUMN IF EXISTS role;
```
