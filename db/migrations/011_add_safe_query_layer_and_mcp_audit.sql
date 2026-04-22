CREATE SCHEMA IF NOT EXISTS safe;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE OR REPLACE VIEW safe.harmonized_observations_v1 AS
SELECT
    upload_session_id::text AS upload_session_id,
    observation_date,
    plot_id,
    variety,
    treatment,
    location,
    variable,
    value::double precision AS value,
    unit,
    normalized_value::double precision AS normalized_value,
    normalized_unit,
    validation_status,
    quality_flags
FROM harmonized.observations;

CREATE TABLE IF NOT EXISTS ops.mcp_tool_audit_log (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    read_only BOOLEAN NOT NULL DEFAULT TRUE,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    sql_text TEXT NULL,
    sql_fingerprint TEXT NULL,
    row_count INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_log_correlation_id
    ON ops.mcp_tool_audit_log (correlation_id);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_log_tool_name
    ON ops.mcp_tool_audit_log (tool_name);
