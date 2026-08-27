CREATE TABLE IF NOT EXISTS composition_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, organization_id),
    UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS composition_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    composition_definition_id UUID NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    previous_version_id UUID REFERENCES composition_versions(id),
    board_grade_code TEXT NOT NULL,
    profile_code TEXT NOT NULL,
    layer_count INTEGER NOT NULL CHECK (layer_count IN (3, 5)),
    composition_signature TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'retired', 'rejected')),
    change_reason TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    FOREIGN KEY (composition_definition_id, organization_id)
        REFERENCES composition_definitions(id, organization_id),
    UNIQUE (id, organization_id),
    UNIQUE (composition_definition_id, version_no),
    CHECK (
        (status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR status <> 'approved'
    )
);

CREATE INDEX IF NOT EXISTS idx_composition_versions_search
ON composition_versions (
    organization_id,
    board_grade_code,
    profile_code,
    status,
    version_no DESC
);

CREATE INDEX IF NOT EXISTS idx_composition_versions_signature
ON composition_versions (organization_id, composition_signature);

CREATE TABLE IF NOT EXISTS composition_layers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    composition_version_id UUID NOT NULL,
    layer_no INTEGER NOT NULL CHECK (layer_no > 0),
    layer_role TEXT NOT NULL,
    material_id UUID NOT NULL,
    material_code_snapshot TEXT NOT NULL,
    material_name_snapshot TEXT NOT NULL,
    gsm_snapshot NUMERIC(8,2) NOT NULL CHECK (gsm_snapshot > 0),
    corrugation_coefficient NUMERIC(10,6) NOT NULL DEFAULT 1
        CHECK (corrugation_coefficient > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (composition_version_id, organization_id)
        REFERENCES composition_versions(id, organization_id) ON DELETE CASCADE,
    FOREIGN KEY (material_id, organization_id)
        REFERENCES materials(id, organization_id),
    UNIQUE (composition_version_id, layer_no)
);

CREATE INDEX IF NOT EXISTS idx_composition_layers_material
ON composition_layers (material_id, composition_version_id);

CREATE TABLE IF NOT EXISTS composition_bct_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_version_id UUID NOT NULL REFERENCES composition_versions(id),
    result_kind TEXT NOT NULL CHECK (result_kind IN ('calculated', 'actual')),
    bct_kn NUMERIC(14,6) NOT NULL CHECK (bct_kn > 0),
    original_value NUMERIC(14,6),
    original_unit TEXT,
    method_code TEXT,
    method_version TEXT,
    sample_count INTEGER CHECK (sample_count IS NULL OR sample_count > 0),
    measured_at TIMESTAMPTZ NOT NULL,
    source_system TEXT NOT NULL,
    source_reference TEXT,
    lab_protocol TEXT,
    recorded_by TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        result_kind <> 'calculated'
        OR (method_code IS NOT NULL AND method_version IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_composition_bct_history
ON composition_bct_results (
    composition_version_id,
    result_kind,
    measured_at DESC,
    created_at DESC
);

CREATE TABLE IF NOT EXISTS composition_cost_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_version_id UUID NOT NULL REFERENCES composition_versions(id),
    total_cost_rub_m2 NUMERIC(16,6) NOT NULL CHECK (total_cost_rub_m2 >= 0),
    material_cost_rub_m2 NUMERIC(16,6) CHECK (material_cost_rub_m2 >= 0),
    conversion_cost_rub_m2 NUMERIC(16,6) CHECK (conversion_cost_rub_m2 >= 0),
    price_effective_at TIMESTAMPTZ NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    calculation_method TEXT NOT NULL,
    source_system TEXT NOT NULL DEFAULT 'ke-box-calc',
    recorded_by TEXT NOT NULL,
    breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_composition_cost_history
ON composition_cost_snapshots (
    composition_version_id,
    price_effective_at DESC,
    calculated_at DESC
);

CREATE OR REPLACE FUNCTION prevent_immutable_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is immutable; append a new version, result or reversal', TG_TABLE_NAME
        USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER stock_movements_are_immutable
BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();

CREATE TRIGGER composition_versions_are_immutable
BEFORE UPDATE OR DELETE ON composition_versions
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();

CREATE TRIGGER composition_layers_are_immutable
BEFORE UPDATE OR DELETE ON composition_layers
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();

CREATE TRIGGER composition_bct_results_are_immutable
BEFORE UPDATE OR DELETE ON composition_bct_results
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();

CREATE TRIGGER composition_cost_snapshots_are_immutable
BEFORE UPDATE OR DELETE ON composition_cost_snapshots
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();
