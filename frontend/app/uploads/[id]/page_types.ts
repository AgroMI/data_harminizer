export type ColumnType = "text" | "numeric" | "date";
export type SemanticRole = "ignore" | "date" | "dimension" | "measure";
export type CanonicalDimension = "plot_id" | "variety" | "treatment" | "location";
export type CanonicalMeasure = "yield" | "moisture" | "plant_height";
export type SupportedUnit = "kg/ha" | "t/ha" | "%" | "cm" | "m";
export type CanonicalUnit = "kg/ha" | "%" | "cm";
export type ValidationStatus = "valid" | "warning" | "invalid";
export type ColumnWarning = "ambiguous_type" | "annotation_like" | "date_parse_issue" | "high_missing";
export type SampleValue = string | number | boolean | null;

export type SampleRow = Record<string, SampleValue>;

export type MissingByColumnItem = {
  column: string;
  missing: number;
  total: number;
  ratio: number;
};

export type DateIssueItem = {
  column: string;
  issue: string;
  example_values: string[];
};

export type ColumnSuggestion = {
  column: string;
  suggested: ColumnType;
  type_override: ColumnType | null;
  semantic_role: SemanticRole;
  canonical_measure: CanonicalMeasure | null;
  canonical_dimension: CanonicalDimension | null;
  unit: SupportedUnit | null;
  warnings: ColumnWarning[];
};

export type PreviewBlock = {
  block_id: string;
  sheet?: string;
  range?: string;
  row_start?: number;
  row_count?: number;
  col_count?: number;
  headers: string[];
  sample_rows: SampleRow[];
  missing_by_column: MissingByColumnItem[];
  type_suggestions: ColumnSuggestion[];
  date_issues: DateIssueItem[];
};

export type PreviewPayload = {
  file_name: string;
  block_count: number;
  blocks: PreviewBlock[];
};

export type SheetManifestItem = {
  sheet_index: number;
  sheet_name: string;
  row_count: number;
  max_column_count: number;
  non_empty_cell_count: number;
  detected_block_count: number;
};

export type RawArtifact = {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  uploaded_at: string;
  parser_version: string;
  storage_type: string;
  storage_path: string | null;
  preview_generated_at: string | null;
  sheet_manifest: SheetManifestItem[];
  parse_warning_summary: string[];
};

export type UploadPreviewResponse = {
  preview: PreviewPayload | null;
  raw_artifact?: RawArtifact | null;
};

export type SaveEditsPayload = {
  columns: Array<{
    block_id: string;
    column: string;
    type_override: ColumnType | null;
    semantic_role: SemanticRole;
    canonical_measure: CanonicalMeasure | null;
    canonical_dimension: CanonicalDimension | null;
    unit: SupportedUnit | null;
  }>;
};

export type CommitResponse = {
  id: string;
  status: "committed";
  staging_rows: number;
  harmonized_rows: number;
};

export type UploadStatus = "preview_ready" | "committed" | "failed";

export type UploadDetailResponse = {
  id: string;
  status: UploadStatus;
  preview: PreviewPayload;
  raw_artifact?: RawArtifact | null;
};

export type QualityObservation = {
  validation_status: ValidationStatus;
  quality_flags: string[];
};

export type QualityObservationResponse = {
  items: QualityObservation[];
  count: number;
};

export type QualitySummary = {
  total: number;
  valid: number;
  warning: number;
  invalid: number;
  flagged: number;
};
