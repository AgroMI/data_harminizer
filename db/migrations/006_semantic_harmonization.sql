DROP TABLE IF EXISTS harmonized.observations;
DROP TABLE IF EXISTS staging.observations;

CREATE TABLE staging.observations (
    upload_session_id uuid NOT NULL REFERENCES raw.upload_sessions(id) ON DELETE CASCADE,
    block_id text NOT NULL,
    source_sheet text NOT NULL,
    source_row_index integer NOT NULL CHECK (source_row_index > 0),
    source_column text NOT NULL,
    observation_date date,
    variable text,
    value numeric,
    unit text,
    dimensions_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE harmonized.observations (
    upload_session_id uuid NOT NULL REFERENCES raw.upload_sessions(id) ON DELETE CASCADE,
    block_id text NOT NULL,
    source_sheet text NOT NULL,
    source_row_index integer NOT NULL CHECK (source_row_index > 0),
    source_column text NOT NULL,
    observation_date date,
    variable text NOT NULL CHECK (length(trim(variable)) > 0),
    value numeric,
    unit text,
    dimensions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (upload_session_id, block_id, source_row_index, source_column)
);
