CREATE TABLE IF NOT EXISTS raw.upload_sessions (
    id uuid PRIMARY KEY,
    uploader_user_id text NOT NULL,
    status text NOT NULL,
    original_filename text NOT NULL,
    preview_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
