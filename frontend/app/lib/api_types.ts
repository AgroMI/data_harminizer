export type UploadListItem = {
  id: string;
  status: string;
  original_filename: string;
  file_size_bytes: number | null;
  sheet_count: number;
  uploaded_at: string | null;
};

export type UploadListResponse = {
  count: number;
  uploads: UploadListItem[];
};

export type CanonicalMeasure = "yield" | "moisture" | "plant_height";
export type CanonicalUnit = "kg/ha" | "%" | "cm";
export type ValidationStatus = "valid" | "warning" | "invalid";
export type QualityFlag =
  | "missing_required_dimension"
  | "missing_observation_date"
  | "missing_unit"
  | "missing_measure_value"
  | "duplicate_candidate"
  | "outlier_candidate";
export type AggregationGroupBy = "variety" | "treatment" | "location" | "validation_status";
export type AggregationMetric = "avg_normalized_value" | "count";

export type HarmonizedObservation = {
  upload_session_id: string;
  observation_date: string | null;
  plot_id: string | null;
  variety: string | null;
  treatment: string | null;
  location: string | null;
  replicate: string | null;
  variable: string | null;
  value: number | null;
  unit: string | null;
  normalized_value: number | null;
  normalized_unit: CanonicalUnit | null;
  validation_status: ValidationStatus;
  quality_flags: QualityFlag[];
  block_id: string;
  source_sheet: string;
  source_row_index: number;
  source_column: string;
};

export type HarmonizedObservationResponse = {
  items: HarmonizedObservation[];
  count: number;
};

export type AggregationItem = {
  group_value: string | null;
  metric_value: number;
  record_count: number;
  normalized_unit: CanonicalUnit | null;
};

export type AggregationResponse = {
  group_by: AggregationGroupBy;
  metric: AggregationMetric;
  include_invalid: boolean;
  items: AggregationItem[];
  count: number;
};

export type QueryMetadata = {
  supported_filters: string[];
  supported_group_bys: AggregationGroupBy[];
  supported_metrics: AggregationMetric[];
  supported_validation_statuses: ValidationStatus[];
  supported_quality_flags: QualityFlag[];
  available_variables: string[];
  available_normalized_units: CanonicalUnit[];
  available_varieties: string[];
  available_locations: string[];
  available_treatments: string[];
  available_plot_ids: string[];
  available_validation_statuses: ValidationStatus[];
  available_quality_flags: QualityFlag[];
  aggregations_exclude_invalid_by_default: boolean;
};

export type MCPToolDefinition = {
  tool_name: string;
  description: string;
  category: string;
  read_only: boolean;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
};

export type MCPToolsResponse = {
  count: number;
  tools: MCPToolDefinition[];
};

export type MCPInvokeResponse = {
  correlation_id: string;
  tool_name: string;
  success: boolean;
  result: Record<string, unknown> | null;
  error: {
    code: string;
    message: string;
    details?: unknown;
  } | null;
  metadata: Record<string, unknown>;
};

export type MCPAuditEntry = {
  correlation_id: string;
  tool_name: string;
  success: boolean;
  read_only: boolean;
  duration_ms: number;
  error_code: string | null;
  sql_fingerprint: string | null;
  row_count: number | null;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
};

export type MCPAuditResponse = {
  count: number;
  items: MCPAuditEntry[];
};

export type TextToSqlGeneratedSql = {
  sql: string;
  parameters: unknown[];
  relation_names: string[];
  projected_columns: string[];
};

export type TextToSqlValidation = {
  valid: boolean;
  normalized_sql: string | null;
  enforced_limit: number | null;
  relation_names: string[];
  issues: Array<{
    code: string;
    message: string;
    severity: string;
  }>;
};

export type TextToSqlExecution = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  truncated: boolean;
  duration_ms: number;
};

export type ToolTraceStep = {
  tool_name: string;
  success: boolean;
  error_code: string | null;
  duration_ms: number | null;
};

export type PipelineMode = "deterministic" | "local_llm_hybrid" | "local_llm_tool_orchestrated";

export type PlanningMetadata = {
  requested_mode: PipelineMode;
  applied_mode: PipelineMode;
  plan_origin: "deterministic" | "local_llm";
  llm_attempted: boolean;
  llm_used: boolean;
  llm_output_valid: boolean | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  orchestration_used: boolean;
  orchestration_steps: string[];
};

export type TextToSqlPipelineResponse = {
  correlation_id: string;
  question: string;
  status: string;
  result_type: string;
  query_plan: Record<string, unknown>;
  generated_sql: TextToSqlGeneratedSql | null;
  validation: TextToSqlValidation | null;
  execution: TextToSqlExecution | null;
  answer: Record<string, unknown>;
  explanation: string[];
  tool_trace: ToolTraceStep[];
  planning_metadata: PlanningMetadata;
};

export type BenchmarkMetric = {
  correct: number;
  total: number;
  accuracy: number;
};

export type BenchmarkQuestionResult = {
  id: string;
  category: string;
  question: string;
  passed: boolean;
  query_plan_match: boolean;
  sql_valid_match: boolean;
  execution_success: boolean;
  answer_match: boolean;
  unsupported_match: boolean;
  unsafe_rejection_match: boolean;
  actual_status: string;
  actual_intent: string;
  actual_result_type: string;
  actual_sql_valid: boolean;
  notes: string | null;
};

export type BenchmarkReport = {
  dataset_name: string;
  total_questions: number;
  query_plan_correctness: BenchmarkMetric;
  sql_validity_rate: BenchmarkMetric;
  execution_success_rate: BenchmarkMetric;
  answer_correctness: BenchmarkMetric;
  unsupported_query_rate: BenchmarkMetric;
  rejected_unsafe_query_rate: BenchmarkMetric;
  questions: BenchmarkQuestionResult[];
};
