CREATE TABLE IF NOT EXISTS ops.llm_planner_audit_log (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    output_valid BOOLEAN NOT NULL DEFAULT FALSE,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    error_code TEXT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_llm_planner_audit_log_correlation_id
    ON ops.llm_planner_audit_log (correlation_id);

CREATE INDEX IF NOT EXISTS idx_llm_planner_audit_log_mode
    ON ops.llm_planner_audit_log (mode);
