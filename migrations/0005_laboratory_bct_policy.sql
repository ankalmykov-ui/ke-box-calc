-- migrate:up

CREATE TABLE laboratory_import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    source_file_id TEXT,
    source_checksum TEXT NOT NULL UNIQUE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'preview'
        CHECK (status IN ('preview', 'applied', 'rejected')),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0)
);

CREATE TABLE laboratory_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_batch_id UUID NOT NULL REFERENCES laboratory_import_batches(id),
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    tested_at DATE,
    technical_card_no TEXT,
    protocol_no TEXT,
    customer TEXT,
    product_type TEXT,
    length_mm INTEGER CHECK (length_mm > 0),
    width_mm INTEGER CHECK (width_mm > 0),
    height_mm INTEGER CHECK (height_mm > 0),
    profile TEXT,
    requested_grade TEXT,
    actual_grade TEXT,
    required_bct_kn NUMERIC(10, 3) CHECK (required_bct_kn > 0),
    actual_bct_kn NUMERIC(10, 3) CHECK (actual_bct_kn > 0),
    normative_ect_kn_m NUMERIC(10, 3) CHECK (normative_ect_kn_m > 0),
    actual_ect_kn_m NUMERIC(10, 3) CHECK (actual_ect_kn_m > 0),
    moisture_percent NUMERIC(6, 3) CHECK (moisture_percent >= 0),
    production_line TEXT,
    customer_requirement TEXT,
    result_status TEXT NOT NULL DEFAULT 'unclassified'
        CHECK (result_status IN ('accepted', 'rejected', 'unclassified')),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (import_batch_id, source_sheet, source_row)
);

CREATE TABLE laboratory_test_layers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    laboratory_test_id UUID NOT NULL REFERENCES laboratory_tests(id) ON DELETE CASCADE,
    layer_index INTEGER NOT NULL CHECK (layer_index > 0),
    layer_role TEXT NOT NULL,
    raw_material_name TEXT NOT NULL,
    normalized_material_name TEXT,
    grammage_g_m2 NUMERIC(8, 2) CHECK (grammage_g_m2 > 0),
    material_id UUID REFERENCES materials(id),
    UNIQUE (laboratory_test_id, layer_index)
);

CREATE INDEX idx_laboratory_tests_comparison
    ON laboratory_tests(profile, length_mm, width_mm, height_mm, requested_grade);
CREATE INDEX idx_laboratory_tests_actual_bct
    ON laboratory_tests(actual_bct_kn) WHERE actual_bct_kn IS NOT NULL;
CREATE INDEX idx_laboratory_test_layers_material
    ON laboratory_test_layers(material_id) WHERE material_id IS NOT NULL;

INSERT INTO calculation_reference_versions(
    reference_code, version, status, payload, source
)
VALUES (
    'optimization_policy',
    'v2.3-working-1',
    'working_reference',
    '{"edge_trim_target_percent":2,"normal_edge_trim_max_percent":3,"allow_elevated_edge_trim":true,"primary_objective":"full_cost","secondary_objective":"bct_margin"}',
    'Решение владельца продукта от 04.09.2026: цена — главный критерий; BCT — обязательный порог и второй критерий; 2–3% — нормальная боковая обрезь, но не жёсткий запрет'
);

-- migrate:down

DELETE FROM calculation_reference_versions
WHERE reference_code = 'optimization_policy' AND version = 'v2.3-working-1';
DROP TABLE IF EXISTS laboratory_test_layers;
DROP TABLE IF EXISTS laboratory_tests;
DROP TABLE IF EXISTS laboratory_import_batches;
