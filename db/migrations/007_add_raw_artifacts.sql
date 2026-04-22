CREATE TABLE IF NOT EXISTS raw.artifacts (
    id uuid PRIMARY KEY,
    original_filename text NOT NULL,
    mime_type text NOT NULL,
    file_size_bytes bigint NOT NULL CHECK (file_size_bytes >= 0),
    file_hash_sha256 text NOT NULL CHECK (length(file_hash_sha256) = 64),
    uploaded_at timestamptz NOT NULL,
    parser_version text NOT NULL,
    storage_type text NOT NULL CHECK (storage_type IN ('db_bytea')),
    storage_path text,
    raw_content bytea NOT NULL,
    sheet_manifest jsonb NOT NULL DEFAULT '[]'::jsonb,
    preview_generated_at timestamptz NOT NULL,
    parse_warning_summary jsonb NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE raw.upload_sessions
ADD COLUMN IF NOT EXISTS artifact_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'upload_sessions_artifact_id_fkey'
    ) THEN
        ALTER TABLE raw.upload_sessions
        ADD CONSTRAINT upload_sessions_artifact_id_fkey
        FOREIGN KEY (artifact_id) REFERENCES raw.artifacts(id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_raw_artifacts_file_hash_sha256
    ON raw.artifacts (file_hash_sha256);

CREATE INDEX IF NOT EXISTS idx_raw_upload_sessions_artifact_id
    ON raw.upload_sessions (artifact_id);
