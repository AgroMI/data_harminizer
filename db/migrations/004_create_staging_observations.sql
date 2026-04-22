CREATE TABLE IF NOT EXISTS staging.observations (
    upload_session_id uuid NOT NULL REFERENCES raw.upload_sessions(id) ON DELETE CASCADE,
    block_id text NOT NULL,
    row_id integer NOT NULL,
    date date,
    variable text,
    value numeric,
    unit text,
    plot_id text
);
