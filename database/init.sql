-- Restaurant Mini App — Database Schema
-- Runs automatically on first PostgreSQL container boot

CREATE TABLE IF NOT EXISTS users (
    telegram_id  BIGINT PRIMARY KEY,
    first_name   VARCHAR(255) NOT NULL,
    last_name    VARCHAR(255),
    username     VARCHAR(255),
    phone_number VARCHAR(50),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS addresses (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    label        VARCHAR(100) NOT NULL DEFAULT 'Home',
    full_address TEXT NOT NULL,
    latitude     VARCHAR(30),
    longitude    VARCHAR(30),
    is_default   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_addresses_user_id ON addresses(user_id);

CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    address_id      UUID REFERENCES addresses(id) ON DELETE SET NULL,
    items           JSONB NOT NULL,
    total_amount    NUMERIC(12, 2) NOT NULL,
    delivery_fee    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    comment         TEXT,
    payment_method  VARCHAR(100) NOT NULL DEFAULT 'cash',
    discriminator   VARCHAR(20) NOT NULL DEFAULT 'delivery',
    alipos_order_id UUID,
    alipos_eats_id  VARCHAR(255),
    status          VARCHAR(50) NOT NULL DEFAULT 'NEW',
    order_number    VARCHAR(50),
    status_updated_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_order_id ON orders(alipos_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_alipos_eats_id ON orders(alipos_eats_id);

-- Stop-list: tracks product availability from AliPOS webhooks
CREATE TABLE IF NOT EXISTS stoplist (
    product_id    UUID NOT NULL,
    restaurant_id UUID NOT NULL,
    count         INT NOT NULL DEFAULT -1,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, restaurant_id)
);
