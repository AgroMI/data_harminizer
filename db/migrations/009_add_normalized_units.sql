ALTER TABLE staging.observations
ADD COLUMN IF NOT EXISTS normalized_value numeric,
ADD COLUMN IF NOT EXISTS normalized_unit text;

ALTER TABLE harmonized.observations
ADD COLUMN IF NOT EXISTS normalized_value numeric,
ADD COLUMN IF NOT EXISTS normalized_unit text;

UPDATE staging.observations
SET
    normalized_value = COALESCE(normalized_value, value),
    normalized_unit = COALESCE(normalized_unit, unit)
WHERE
    normalized_value IS NULL
    OR normalized_unit IS NULL;

UPDATE harmonized.observations
SET
    normalized_value = COALESCE(normalized_value, value),
    normalized_unit = COALESCE(normalized_unit, unit)
WHERE
    normalized_value IS NULL
    OR normalized_unit IS NULL;

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_normalized_unit
    ON harmonized.observations (normalized_unit);
