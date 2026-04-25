from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypedDict

ColumnType = Literal["text", "numeric", "date"]
SemanticRole = Literal["ignore", "date", "dimension", "measure"]
CanonicalDimension = Literal["plot_id", "variety", "treatment", "location", "replicate"]
CanonicalMeasure = Literal["yield", "moisture", "plant_height"]
SupportedUnit = Literal["kg/ha", "t/ha", "kg/parc", "%", "cm", "m"]
CanonicalUnit = Literal["kg/ha", "%", "cm"]
ValidationStatus = Literal["valid", "warning", "invalid"]
QualityFlag = Literal[
    "missing_required_dimension",
    "missing_observation_date",
    "missing_unit",
    "missing_measure_value",
    "duplicate_candidate",
    "outlier_candidate",
]
ColumnWarningCode = Literal[
    "ambiguous_type",
    "annotation_like",
    "date_parse_issue",
    "high_missing",
]
DataRow = dict[str, Any]


class WorkbookSheet(TypedDict):
    sheet_index: int
    sheet_name: str
    rows: list[list[Any]]


class SheetManifestItem(TypedDict):
    sheet_index: int
    sheet_name: str
    row_count: int
    max_column_count: int
    non_empty_cell_count: int
    detected_block_count: int


class BlockRecord(TypedDict):
    block_id: str
    sheet_name: str
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    row_count: int
    col_count: int
    rows: list[list[Any]]


class MissingByColumnItem(TypedDict):
    column: str
    missing: int
    total: int
    ratio: float


class TypeSuggestionItem(TypedDict):
    column: str
    suggested: ColumnType
    type_override: ColumnType | None
    semantic_role: SemanticRole
    canonical_measure: CanonicalMeasure | None
    canonical_dimension: CanonicalDimension | None
    unit: SupportedUnit | None
    warnings: list[ColumnWarningCode]


class DateIssueItem(TypedDict):
    column: str
    issue: str
    example_values: list[str]


class ExtractedTable(TypedDict):
    headers: list[str]
    data_rows: list[DataRow]
    header_in_first_row: bool
    header_row_count: int
    data_row_start_index: int
    inferred_unit: str | None
    inferred_year: int | None


class PublicPreviewBlock(TypedDict):
    block_id: str
    sheet: str
    range: str
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    row_count: int
    col_count: int
    headers: list[str]
    sample_rows: list[DataRow]
    missing_by_column: list[MissingByColumnItem]
    type_suggestions: list[TypeSuggestionItem]
    date_issues: list[DateIssueItem]
    inferred_year: int | None


class PreviewBlock(PublicPreviewBlock):
    _cells: list[list[Any]]


class PublicPreviewPayload(TypedDict):
    file_name: str
    block_count: int
    blocks: list[PublicPreviewBlock]
    year_override: int | None


class PreviewPayload(TypedDict):
    file_name: str
    block_count: int
    blocks: list[PreviewBlock]
    year_override: int | None


class ParsedUploadSource(TypedDict):
    preview: PreviewPayload
    parser_version: str
    sheet_manifest: list[SheetManifestItem]
    preview_generated_at: datetime
    parse_warning_summary: list[str]
