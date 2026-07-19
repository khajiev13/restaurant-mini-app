ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS invoice_cancel_status VARCHAR(32);
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_updated_at TIMESTAMP;
