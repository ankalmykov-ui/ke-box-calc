-- migrate:up

CREATE TABLE materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    material_type TEXT NOT NULL CHECK (material_type IN ('paper', 'liner')),
    grammage_g_m2 NUMERIC(8, 2) NOT NULL CHECK (grammage_g_m2 > 0),
    width_mm INTEGER NOT NULL CHECK (width_mm > 0),
    manufacturer TEXT,
    classification_status TEXT NOT NULL DEFAULT 'preliminary'
        CHECK (classification_status IN ('preliminary', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, width_mm)
);

CREATE TABLE material_price_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID NOT NULL REFERENCES materials(id),
    price_rub_kg NUMERIC(12, 4) NOT NULL CHECK (price_rub_kg >= 0),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    source TEXT NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX uq_material_active_price
    ON material_price_versions(material_id) WHERE valid_to IS NULL;

CREATE TABLE stock_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type TEXT NOT NULL CHECK (document_type IN ('opening_balance', 'receipt', 'adjustment')),
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('preview', 'posted', 'cancelled')),
    source_name TEXT,
    source_checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at TIMESTAMPTZ,
    UNIQUE NULLS NOT DISTINCT (document_type, source_checksum)
);

CREATE TABLE stock_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES stock_documents(id),
    material_id UUID NOT NULL REFERENCES materials(id),
    quantity_kg NUMERIC(14, 3) NOT NULL,
    unit_cost_rub_kg NUMERIC(12, 4) CHECK (unit_cost_rub_kg >= 0),
    movement_type TEXT NOT NULL CHECK (movement_type IN ('receipt', 'writeoff', 'adjustment', 'reversal')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_stock_movements_material ON stock_movements(material_id, occurred_at);

-- migrate:down

DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS stock_documents;
DROP TABLE IF EXISTS material_price_versions;
DROP TABLE IF EXISTS materials;
