-- migrate:up

ALTER TABLE material_price_versions
ADD COLUMN quality_status TEXT NOT NULL DEFAULT 'preliminary'
    CHECK (quality_status IN ('approved', 'preliminary', 'requires_verification'));

UPDATE material_price_versions
SET quality_status = 'requires_verification'
WHERE price_rub_kg < 20 OR price_rub_kg > 200;

INSERT INTO calculation_reference_versions(reference_code, version, status, payload, source)
VALUES (
    'price_quality',
    'v2.2-working-1',
    'requires_verification',
    '{"plausible_min_rub_kg":20,"plausible_max_rub_kg":200}',
    'Протокол предварительного импорта остатков 28.08.2026; границы уточнить'
);

-- migrate:down

DELETE FROM calculation_reference_versions WHERE reference_code = 'price_quality';
ALTER TABLE material_price_versions DROP COLUMN IF EXISTS quality_status;
