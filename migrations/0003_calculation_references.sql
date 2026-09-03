-- migrate:up

CREATE TABLE calculation_reference_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference_code TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'working_reference', 'requires_verification')),
    payload JSONB NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    source TEXT NOT NULL,
    UNIQUE (reference_code, version),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX uq_calculation_reference_active
    ON calculation_reference_versions(reference_code) WHERE valid_to IS NULL;

INSERT INTO calculation_reference_versions(reference_code, version, status, payload, source)
VALUES
(
    'fefco_0201',
    'v2.2-working-1',
    'working_reference',
    '{"manufacturer_joint_mm":37,"rounding":"half_up_1_mm","flute_direction":"along_box_height"}',
    'KE | BOX CALC ТЗ v2.2; контрольная техкарта №990'
),
(
    'profiles',
    'v2.2-working-1',
    'working_reference',
    '{"E":{"caliper_mm":1.73,"flute_factor":1.47},"B":{"caliper_mm":2.97,"flute_factor":1.47},"C":{"caliper_mm":4.02,"flute_factor":1.47},"BE":{"caliper_mm":4.19,"flute_factor":1.47},"CE":{"caliper_mm":5.24,"flute_factor":1.47},"BC":{"caliper_mm":6.72,"flute_factor":1.47}}',
    'Толщины: KE | BOX CALC ТЗ v2.2; коэффициенты гофрирования требуют проверки технологом'
),
(
    'corrugator',
    'v2.2-working-1',
    'working_reference',
    '{"working_width_mm":2100,"max_streams":5,"crosscut_levels":2,"technological_trim_min_mm":0,"technological_trim_max_mm":50}',
    'Рабочий справочник гофроагрегата Руспак; требует производственной сверки'
),
(
    'board_grades',
    'v2.2-working-1',
    'requires_verification',
    '{"T21":2.2,"T22":3.0,"T23.1":3.8,"T23.2":4.1,"T23.3":4.4,"T24.1":4.6,"T24.2":4.9,"T24.3":5.2,"T25.1":5.4,"T25.2":5.7,"T25.3":6.0,"T26.1":6.2,"T26.2":6.5,"T26.3":6.8,"T27.1":7.0,"T27.2":7.3,"T27.3":7.6,"P31":5.0,"P32/1":6.0,"P32/2":7.0,"P33":8.0}',
    'Рабочая лабораторная таблица предыдущей версии; подтвердить ответственным технологом'
);

-- migrate:down

DROP TABLE IF EXISTS calculation_reference_versions;
