CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS machines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    line_name TEXT NOT NULL,
    model TEXT,
    manufacturer TEXT,
    machine_type TEXT,
    data_status TEXT NOT NULL DEFAULT 'requires_verification',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machine_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id UUID NOT NULL REFERENCES machines(id),
    parameter_code TEXT NOT NULL,
    parameter_name TEXT NOT NULL,
    passport_value TEXT,
    actual_value TEXT,
    unit TEXT,
    status TEXT NOT NULL,
    valid_from DATE,
    valid_to DATE,
    source_name TEXT,
    comment TEXT,
    use_in_calc BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_machine_parameters_machine
ON machine_parameters(machine_id, parameter_code);

CREATE TABLE IF NOT EXISTS raw_materials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_1c TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT,
    manufacturer TEXT,
    supplier TEXT,
    paper_type TEXT,
    gsm NUMERIC(8,2),
    roll_width_mm NUMERIC(10,2),
    classification_status TEXT NOT NULL DEFAULT 'requires_classification',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_material_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_material_id UUID NOT NULL REFERENCES raw_materials(id),
    price_rub_t NUMERIC(14,2),
    stock_kg NUMERIC(14,3),
    procurement_status TEXT,
    effective_at TIMESTAMPTZ NOT NULL,
    import_batch_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corrugation_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT,
    corrugation_coefficient NUMERIC(8,4),
    status TEXT NOT NULL DEFAULT 'approved',
    valid_from DATE,
    valid_to DATE
);

CREATE TABLE IF NOT EXISTS board_grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS board_grade_norms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    board_grade_id UUID NOT NULL REFERENCES board_grades(id),
    metric_code TEXT NOT NULL,
    min_value NUMERIC(14,4),
    max_value NUMERIC(14,4),
    unit TEXT,
    valid_from DATE,
    valid_to DATE,
    source_name TEXT
);

CREATE TABLE IF NOT EXISTS lab_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_test_key TEXT UNIQUE,
    test_date DATE,
    order_ref TEXT,
    product_ref TEXT,
    declared_grade TEXT,
    profile_code TEXT,
    ect NUMERIC(14,4),
    bct NUMERIC(14,4),
    passed BOOLEAN,
    source_file TEXT,
    source_row TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lab_test_layers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_test_id UUID NOT NULL REFERENCES lab_tests(id) ON DELETE CASCADE,
    layer_no INTEGER NOT NULL,
    layer_role TEXT,
    raw_material_code_1c TEXT,
    source_material_name TEXT,
    normalized_material_name TEXT,
    gsm NUMERIC(8,2)
);

CREATE TABLE IF NOT EXISTS import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_type TEXT NOT NULL,
    file_name TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    rows_total INTEGER,
    rows_new INTEGER,
    rows_changed INTEGER,
    rows_errors INTEGER
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_ref TEXT,
    planning_date DATE,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_type TEXT NOT NULL,
    length_mm NUMERIC(10,2),
    width_mm NUMERIC(10,2),
    height_mm NUMERIC(10,2),
    quantity INTEGER NOT NULL,
    required_board_grade TEXT,
    blank_length_mm NUMERIC(10,2),
    blank_width_mm NUMERIC(10,2),
    blank_area_m2 NUMERIC(14,6)
);

CREATE TABLE IF NOT EXISTS calculations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calculation_no BIGSERIAL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft',
    input_snapshot JSONB NOT NULL,
    result_snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO machines(code, line_name, model, manufacturer, machine_type, data_status)
VALUES
('M001','P660','P660 660×1800','LMC (по внутреннему справочнику)','Flexo Folder Gluer + slotter + rotary die cutter','passport_confirmed'),
('M002','2Print','TP-CR-0924','TOPRINT / TOPRA — проверить','Flexo Printer Slotter','requires_verification'),
('M003','SR PACK','FFG-1226','SR PACK — проверить','Flexo + slotter + die cutter + folder/gluer','passport_confirmed')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS commercial_price_reference (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier TEXT NOT NULL,
    gsm_text TEXT,
    price_rub_t NUMERIC(14,2),
    price_rub_t_max NUMERIC(14,2),
    procurement_status TEXT,
    source_name TEXT NOT NULL,
    effective_at DATE,
    eligible_for_composition BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fefco_profile_geometry_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    construction_code TEXT NOT NULL DEFAULT '0201',
    profile_code TEXT NOT NULL,
    caliper_mm NUMERIC(8,3),
    n_long_mm NUMERIC(8,3),
    body_allowance_mm NUMERIC(8,3),
    glue_flap_mm NUMERIC(8,3),
    glue_gap_mm NUMERIC(8,3),
    rounding_mode TEXT NOT NULL DEFAULT 'ceil_each_dimension_mm',
    status TEXT NOT NULL,
    source_name TEXT,
    valid_from DATE,
    valid_to DATE,
    comment TEXT,
    UNIQUE(construction_code, profile_code, valid_from)
);

ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS variant_1c TEXT;
ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS technological_code TEXT;
ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS color TEXT;
ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS procurement_status TEXT NOT NULL DEFAULT 'requires_classification';
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_materials_1c_variant ON raw_materials(code_1c, COALESCE(variant_1c, ''));

CREATE TABLE IF NOT EXISTS composition_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    board_grade TEXT NOT NULL,
    profile_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    evidence TEXT NOT NULL DEFAULT 'technologist_approved',
    strength_reserve_pct NUMERIC(8,3),
    lab_pass_count INTEGER NOT NULL DEFAULT 0,
    comment TEXT,
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS composition_template_layers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_template_id UUID NOT NULL REFERENCES composition_templates(id) ON DELETE CASCADE,
    layer_no INTEGER NOT NULL,
    role TEXT NOT NULL,
    raw_material_id UUID NOT NULL REFERENCES raw_materials(id),
    corrugation_coefficient NUMERIC(8,4) NOT NULL DEFAULT 1,
    UNIQUE(composition_template_id, layer_no)
);
CREATE INDEX IF NOT EXISTS idx_composition_templates_grade_profile ON composition_templates(board_grade, profile_code, status);

ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS actual_grade TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS composition_key TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS ect_norm NUMERIC(14,4);
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS moisture NUMERIC(14,4);
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS tech_card TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS protocol TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS client TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS line TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS customer_requirement TEXT;
ALTER TABLE lab_tests ADD COLUMN IF NOT EXISTS import_batch_id UUID;
CREATE INDEX IF NOT EXISTS idx_lab_tests_composition ON lab_tests(composition_key, profile_code, declared_grade);
CREATE INDEX IF NOT EXISTS idx_lab_tests_date ON lab_tests(test_date);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS planning_horizon_days INTEGER NOT NULL DEFAULT 1;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS item_code TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS profile_code TEXT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS colors INTEGER NOT NULL DEFAULT 1;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS die_cut BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS machine_cost_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id UUID NOT NULL REFERENCES machines(id),
    hourly_cost_rub NUMERIC(14,2) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    status TEXT NOT NULL DEFAULT 'working',
    source_name TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corrugator_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parameter_code TEXT NOT NULL,
    value_numeric NUMERIC(14,4),
    value_text TEXT,
    unit TEXT,
    status TEXT NOT NULL DEFAULT 'working',
    valid_from DATE,
    valid_to DATE,
    source_name TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
