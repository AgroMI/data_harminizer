ALTER TABLE staging.observations
ADD COLUMN IF NOT EXISTS plot_id text,
ADD COLUMN IF NOT EXISTS variety text,
ADD COLUMN IF NOT EXISTS treatment text,
ADD COLUMN IF NOT EXISTS location text;

ALTER TABLE harmonized.observations
ADD COLUMN IF NOT EXISTS plot_id text,
ADD COLUMN IF NOT EXISTS variety text,
ADD COLUMN IF NOT EXISTS treatment text,
ADD COLUMN IF NOT EXISTS location text;

UPDATE staging.observations
SET
    plot_id = COALESCE(plot_id, dimensions_json ->> 'plot_id'),
    variety = COALESCE(variety, dimensions_json ->> 'variety'),
    treatment = COALESCE(treatment, dimensions_json ->> 'treatment'),
    location = COALESCE(location, dimensions_json ->> 'location')
WHERE
    plot_id IS NULL
    OR variety IS NULL
    OR treatment IS NULL
    OR location IS NULL;

UPDATE harmonized.observations
SET
    plot_id = COALESCE(plot_id, dimensions_json ->> 'plot_id'),
    variety = COALESCE(variety, dimensions_json ->> 'variety'),
    treatment = COALESCE(treatment, dimensions_json ->> 'treatment'),
    location = COALESCE(location, dimensions_json ->> 'location')
WHERE
    plot_id IS NULL
    OR variety IS NULL
    OR treatment IS NULL
    OR location IS NULL;

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_variable
    ON harmonized.observations (variable);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_variety
    ON harmonized.observations (variety);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_treatment
    ON harmonized.observations (treatment);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_location
    ON harmonized.observations (location);

CREATE INDEX IF NOT EXISTS idx_harmonized_observations_observation_date
    ON harmonized.observations (observation_date);
