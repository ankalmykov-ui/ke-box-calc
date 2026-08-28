CREATE INDEX IF NOT EXISTS idx_material_price_history_current
ON material_price_history (
    material_id,
    valid_from DESC,
    created_at DESC
);

CREATE TRIGGER material_price_history_is_immutable
BEFORE UPDATE OR DELETE ON material_price_history
FOR EACH ROW EXECUTE FUNCTION prevent_immutable_history_mutation();
