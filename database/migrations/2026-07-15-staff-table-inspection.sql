ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_check_attempted_at TIMESTAMP;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_checked_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_orders_inplace_workspace
    ON orders(table_id, alipos_sync_status, status, alipos_status_check_attempted_at)
    WHERE discriminator = 'inplace';
