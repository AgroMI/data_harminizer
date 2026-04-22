ALTER TABLE staging.observations
ADD COLUMN IF NOT EXISTS validation_status text NOT NULL DEFAULT 'valid',
ADD COLUMN IF NOT EXISTS quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE harmonized.observations
ADD COLUMN IF NOT EXISTS validation_status text NOT NULL DEFAULT 'valid',
ADD COLUMN IF NOT EXISTS quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE staging.observations
SET
    validation_status = COALESCE(NULLIF(trim(validation_status), ''), 'valid'),
    quality_flags = COALESCE(quality_flags, '[]'::jsonb)
WHERE
    validation_status IS NULL
    OR trim(validation_status) = ''
    OR quality_flags IS NULL;

UPDATE harmonized.observations
SET
    validation_status = COALESCE(NULLIF(trim(validation_status), ''), 'valid'),
    quality_flags = COALESCE(quality_flags, '[]'::jsonb)
WHERE
    validation_status IS NULL
    OR trim(validation_status) = ''
    OR quality_flags IS NULL;

CREATE INDEX IF NOT EXISTS idx_staging_observations_validation_status
    ON staging.observations (validation_status);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_validation_status
    ON harmonized.observations (validation_status);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_quality_flags
    ON harmonized.observations USING GIN (quality_flags);
