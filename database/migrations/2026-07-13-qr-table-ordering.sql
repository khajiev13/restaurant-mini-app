ALTER TABLE orders ADD COLUMN IF NOT EXISTS items_cost NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_info JSONB;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_id UUID;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_title VARCHAR(100);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hall_id UUID;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hall_title VARCHAR(100);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS service_percent NUMERIC(5, 2) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_access_expires_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_sync_status VARCHAR(32);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_sync_error TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_request_id UUID;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS refund_sync_status VARCHAR(32);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS refund_sync_error TEXT;

CREATE INDEX IF NOT EXISTS idx_orders_table_id ON orders(table_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_sync_status ON orders(alipos_sync_status);
CREATE INDEX IF NOT EXISTS idx_orders_refund_sync_status ON orders(refund_sync_status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_user_request
    ON orders(user_id, client_request_id)
    WHERE client_request_id IS NOT NULL;
