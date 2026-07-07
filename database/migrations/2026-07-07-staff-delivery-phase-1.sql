ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'customer';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_staff_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_users_role_valid'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT ck_users_role_valid
            CHECK (role IN ('customer', 'staff', 'admin'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_orders_assigned_staff_id ON orders(assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_staff_available ON orders(status, assigned_staff_id, discriminator);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_one_active_delivery_per_staff
    ON orders(assigned_staff_id)
    WHERE assigned_staff_id IS NOT NULL
      AND delivered_at IS NULL
      AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED');
