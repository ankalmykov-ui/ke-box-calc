CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS warehouses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, code)
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    external_subject TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, external_subject)
);

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_role_scopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id),
    site_id UUID REFERENCES sites(id),
    warehouse_id UUID REFERENCES warehouses(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (user_id, role_id, site_id, warehouse_id)
);

CREATE TABLE IF NOT EXISTS materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    technological_designation TEXT,
    material_type TEXT NOT NULL,
    gsm NUMERIC(8,2) NOT NULL CHECK (gsm > 0),
    color TEXT,
    surface_type TEXT,
    manufacturer TEXT,
    supplier TEXT,
    procurement_status TEXT NOT NULL DEFAULT 'requires_classification'
        CHECK (procurement_status IN (
            'purchased',
            'temporarily_not_purchased',
            'stock_only',
            'unavailable',
            'requires_classification'
        )),
    classification_status TEXT NOT NULL DEFAULT 'requires_classification'
        CHECK (classification_status IN ('approved', 'requires_classification', 'rejected')),
    source_name TEXT,
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (id, organization_id),
    UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS material_external_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    material_id UUID NOT NULL,
    source_system TEXT NOT NULL,
    external_code TEXT NOT NULL,
    external_variant TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (material_id, organization_id)
        REFERENCES materials(id, organization_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_material_external_identifier
ON material_external_identifiers (
    organization_id,
    source_system,
    external_code,
    COALESCE(external_variant, '')
);

CREATE TABLE IF NOT EXISTS material_widths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    width_mm NUMERIC(10,2) NOT NULL CHECK (width_mm > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'requires_verification')),
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,
    source_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (material_id, width_mm, valid_from)
);

CREATE TABLE IF NOT EXISTS material_price_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    unit_code TEXT NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'RUB',
    price_per_unit NUMERIC(16,4) NOT NULL CHECK (price_per_unit >= 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    source_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX IF NOT EXISTS idx_material_price_history_period
ON material_price_history (material_id, valid_from DESC);

CREATE TABLE IF NOT EXISTS material_lots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id UUID NOT NULL REFERENCES warehouses(id),
    material_id UUID NOT NULL REFERENCES materials(id),
    lot_code TEXT NOT NULL,
    supplier_lot_code TEXT,
    received_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'quarantine', 'blocked', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (warehouse_id, material_id, lot_code)
);

CREATE TABLE IF NOT EXISTS material_rolls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_id UUID NOT NULL REFERENCES material_lots(id),
    roll_code TEXT NOT NULL,
    width_mm NUMERIC(10,2) NOT NULL CHECK (width_mm > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'quarantine', 'blocked', 'consumed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lot_id, roll_code)
);

CREATE TABLE IF NOT EXISTS unit_conversion_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID REFERENCES materials(id) ON DELETE CASCADE,
    from_unit TEXT NOT NULL,
    to_unit TEXT NOT NULL,
    factor NUMERIC(18,8) NOT NULL CHECK (factor > 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    source_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_unit <> to_unit),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS stock_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    warehouse_id UUID NOT NULL REFERENCES warehouses(id),
    document_type TEXT NOT NULL
        CHECK (document_type IN ('receipt', 'writeoff', 'inventory_adjustment', 'reversal')),
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('draft', 'posted', 'reversed', 'cancelled')),
    idempotency_key TEXT NOT NULL,
    source_system TEXT NOT NULL DEFAULT 'manual',
    source_reference TEXT,
    reason TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at TIMESTAMPTZ,
    reversal_of_document_id UUID REFERENCES stock_documents(id),
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (reversal_of_document_id)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES stock_documents(id),
    warehouse_id UUID NOT NULL REFERENCES warehouses(id),
    material_id UUID NOT NULL REFERENCES materials(id),
    lot_id UUID REFERENCES material_lots(id),
    roll_id UUID REFERENCES material_rolls(id),
    movement_kind TEXT NOT NULL
        CHECK (movement_kind IN ('receipt', 'writeoff', 'inventory_adjustment', 'reversal')),
    quantity NUMERIC(18,6) NOT NULL CHECK (quantity <> 0),
    unit_code TEXT NOT NULL,
    base_quantity_kg NUMERIC(18,6) NOT NULL CHECK (base_quantity_kg <> 0),
    unit_price NUMERIC(16,4),
    currency_code CHAR(3) NOT NULL DEFAULT 'RUB',
    source_line_no INTEGER NOT NULL CHECK (source_line_no > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, source_line_no),
    CHECK (
        (quantity > 0 AND base_quantity_kg > 0)
        OR (quantity < 0 AND base_quantity_kg < 0)
    ),
    CHECK (
        (movement_kind = 'receipt' AND base_quantity_kg > 0)
        OR (movement_kind = 'writeoff' AND base_quantity_kg < 0)
        OR movement_kind = 'inventory_adjustment'
        OR movement_kind = 'reversal'
    )
);

CREATE INDEX IF NOT EXISTS idx_stock_movements_balance
ON stock_movements (warehouse_id, material_id, lot_id, roll_id);

CREATE OR REPLACE VIEW stock_balances AS
SELECT
    warehouse_id,
    material_id,
    lot_id,
    roll_id,
    SUM(base_quantity_kg) AS balance_kg,
    MAX(created_at) AS last_movement_at
FROM stock_movements
GROUP BY warehouse_id, material_id, lot_id, roll_id;

-- v0.8 used the same table name for a smaller, session-oriented import log.
-- Preserve it verbatim when upgrading an existing database; v0.9 starts a new
-- stable import contract under the canonical name below.
DO $$
BEGIN
    IF to_regclass('public.import_batches') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'import_batches'
             AND column_name = 'organization_id'
       ) THEN
        ALTER TABLE import_batches RENAME TO import_batches_v08_legacy;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    warehouse_id UUID REFERENCES warehouses(id),
    import_type TEXT NOT NULL CHECK (import_type IN ('materials', 'inventory', 'laboratory')),
    source_system TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_checksum TEXT NOT NULL,
    template_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'preview' CHECK (status IN ('preview', 'validated', 'applied', 'rejected')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    UNIQUE (organization_id, import_type, file_checksum)
);

CREATE TABLE IF NOT EXISTS import_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_batch_id UUID NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_no INTEGER NOT NULL CHECK (row_no > 0),
    raw_data JSONB NOT NULL,
    normalized_data JSONB,
    status TEXT NOT NULL CHECK (status IN ('valid', 'warning', 'error', 'applied')),
    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (import_batch_id, row_no)
);

CREATE TABLE IF NOT EXISTS inventory_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_document_id UUID NOT NULL UNIQUE REFERENCES stock_documents(id),
    import_batch_id UUID REFERENCES import_batches(id),
    counted_at TIMESTAMPTZ NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_document_id UUID NOT NULL REFERENCES inventory_documents(id) ON DELETE CASCADE,
    material_id UUID NOT NULL REFERENCES materials(id),
    lot_id UUID REFERENCES material_lots(id),
    roll_id UUID REFERENCES material_rolls(id),
    accounting_quantity_kg NUMERIC(18,6) NOT NULL,
    actual_quantity_kg NUMERIC(18,6) NOT NULL CHECK (actual_quantity_kg >= 0),
    adjustment_quantity_kg NUMERIC(18,6) NOT NULL,
    source_line_no INTEGER NOT NULL,
    UNIQUE (inventory_document_id, source_line_no),
    CHECK (adjustment_quantity_kg = actual_quantity_kg - accounting_quantity_kg)
);

CREATE TABLE IF NOT EXISTS writeoff_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_document_id UUID NOT NULL UNIQUE REFERENCES stock_documents(id),
    order_reference TEXT,
    layout_variant_reference TEXT,
    calculation_snapshot_id UUID,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'reversed')),
    confirmed_by TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_snapshot JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    reason TEXT,
    before_data JSONB,
    after_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity
ON audit_log (organization_id, entity_type, entity_id, created_at DESC);

INSERT INTO roles (code, name)
VALUES
    ('manager', 'Менеджер'),
    ('technologist', 'Технолог'),
    ('warehouse', 'Складской пользователь'),
    ('administrator', 'Администратор')
ON CONFLICT (code) DO NOTHING;
