CREATE TABLE IF NOT EXISTS harmonized.observations (
    upload_session_id uuid NOT NULL REFERENCES raw.upload_sessions(id) ON DELETE CASCADE,
    block_id text NOT NULL,
    row_id integer NOT NULL CHECK (row_id >= 0),
    date date,
    variable text NOT NULL CHECK (length(trim(variable)) > 0),
    value numeric,
    unit text,
    plot_id text,
    PRIMARY KEY (upload_session_id, block_id, row_id)
);
