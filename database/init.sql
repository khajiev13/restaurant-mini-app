-- Restaurant Mini App — Database Schema
-- Runs automatically on first PostgreSQL container boot

CREATE TABLE IF NOT EXISTS users (
    telegram_id  BIGINT PRIMARY KEY,
    first_name   VARCHAR(255) NOT NULL,
    last_name    VARCHAR(255),
    username     VARCHAR(255),
    phone_number VARCHAR(50),
    language     VARCHAR(5) NOT NULL DEFAULT 'uz',
    role         VARCHAR(32) NOT NULL DEFAULT 'customer',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_users_role_valid CHECK (role IN ('customer', 'staff', 'admin'))
);

CREATE TABLE IF NOT EXISTS addresses (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    label        VARCHAR(100) NOT NULL DEFAULT 'Home',
    full_address TEXT NOT NULL,
    latitude     VARCHAR(30),
    longitude    VARCHAR(30),
    entrance     VARCHAR(50),
    apartment    VARCHAR(50),
    floor        VARCHAR(20),
    door_code    VARCHAR(50),
    courier_instructions TEXT,
    is_default   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_addresses_user_id ON addresses(user_id);

CREATE TABLE IF NOT EXISTS orders (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    address_id             UUID REFERENCES addresses(id) ON DELETE SET NULL,
    assigned_staff_id      BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    assigned_at            TIMESTAMP,
    delivered_at           TIMESTAMP,
    items                  JSONB NOT NULL,
    items_cost             NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_amount           NUMERIC(12, 2) NOT NULL,
    delivery_fee           NUMERIC(12, 2) NOT NULL DEFAULT 0,
    comment                TEXT,
    payment_method         VARCHAR(100) NOT NULL DEFAULT 'cash',
    payment_provider       VARCHAR(50),
    payment_status         VARCHAR(50),
    payment_expires_at     TIMESTAMP,
    payment_paid_at        TIMESTAMP,
    payment_error          TEXT,
    payment_card_pan       VARCHAR(32),
    payment_ps             VARCHAR(50),
    discriminator          VARCHAR(20) NOT NULL DEFAULT 'delivery',
    table_id               UUID,
    table_title            VARCHAR(100),
    hall_id                UUID,
    hall_title             VARCHAR(100),
    service_percent        NUMERIC(5, 2) NOT NULL DEFAULT 0,
    alipos_order_id        UUID,
    alipos_eats_id         VARCHAR(255),
    alipos_sync_status     VARCHAR(32),
    alipos_sync_error      TEXT,
    multicard_invoice_uuid VARCHAR(64),
    multicard_checkout_url TEXT,
    multicard_receipt_url  TEXT,
    multicard_payment_uuid VARCHAR(64),
    alipos_cancel_status   VARCHAR(50),
    alipos_cancel_error    TEXT,
    status                 VARCHAR(50) NOT NULL DEFAULT 'NEW',
    order_number           VARCHAR(50),
    status_updated_at      TIMESTAMP,
    cancel_requested_at    TIMESTAMP,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_order_id ON orders(alipos_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_eats_id ON orders(alipos_eats_id);
CREATE INDEX IF NOT EXISTS idx_orders_table_id ON orders(table_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_sync_status ON orders(alipos_sync_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_expires_at ON orders(payment_expires_at);
CREATE INDEX IF NOT EXISTS idx_orders_multicard_payment_uuid ON orders(multicard_payment_uuid);
CREATE INDEX IF NOT EXISTS idx_orders_assigned_staff_id ON orders(assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_staff_available ON orders(status, assigned_staff_id, discriminator);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_one_active_delivery_per_staff
    ON orders(assigned_staff_id)
    WHERE assigned_staff_id IS NOT NULL
      AND discriminator = 'delivery'
      AND delivered_at IS NULL
      AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED');

-- Stop-list: tracks product availability from AliPOS webhooks
CREATE TABLE IF NOT EXISTS stoplist (
    product_id    UUID NOT NULL,
    restaurant_id UUID NOT NULL,
    count         INT NOT NULL DEFAULT -1,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, restaurant_id)
);

-- Migration: add language column to existing databases
ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(5) NOT NULL DEFAULT 'uz';
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'customer';

-- Migration: add Multicard / Rahmat payment columns to existing databases
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_provider       VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status         VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_expires_at     TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_paid_at        TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_error          TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_card_pan       VARCHAR(32);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_ps             VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS multicard_invoice_uuid VARCHAR(64);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS multicard_checkout_url TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS multicard_receipt_url  TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS multicard_payment_uuid VARCHAR(64);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_cancel_status   VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_cancel_error    TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_staff_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS items_cost NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_id UUID;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS table_title VARCHAR(100);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hall_id UUID;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hall_title VARCHAR(100);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS service_percent NUMERIC(5, 2) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_sync_status VARCHAR(32);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS alipos_sync_error TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMP;

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

CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_expires_at ON orders(payment_expires_at);
CREATE INDEX IF NOT EXISTS idx_orders_multicard_payment_uuid ON orders(multicard_payment_uuid);
CREATE INDEX IF NOT EXISTS idx_orders_assigned_staff_id ON orders(assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_staff_available ON orders(status, assigned_staff_id, discriminator);
CREATE INDEX IF NOT EXISTS idx_orders_table_id ON orders(table_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_sync_status ON orders(alipos_sync_status);
DROP INDEX IF EXISTS uq_orders_one_active_delivery_per_staff;
CREATE UNIQUE INDEX uq_orders_one_active_delivery_per_staff
    ON orders(assigned_staff_id)
    WHERE assigned_staff_id IS NOT NULL
      AND discriminator = 'delivery'
      AND delivered_at IS NULL
      AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED');
