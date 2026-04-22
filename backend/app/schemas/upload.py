from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.common import ColumnType, UploadStatus
from etl.semantic_mapping import CANONICAL_DIMENSIONS, CANONICAL_MEASURES
from etl.types import (
    CanonicalDimension,
    CanonicalMeasure,
    PublicPreviewPayload,
    SemanticRole,
    SupportedUnit,
)
from etl.unit_harmonization import is_supported_unit_for_measure, normalize_supported_unit


class ColumnEditItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    column: str = Field(min_length=1)
    type_override: ColumnType | None = None
    semantic_role: SemanticRole
    canonical_measure: CanonicalMeasure | None = None
    canonical_dimension: CanonicalDimension | None = None
    unit: SupportedUnit | None = None

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_optional_unit(cls, value: str | None) -> SupportedUnit | str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None

        normalized = normalize_supported_unit(cleaned)
        if normalized is not None:
            return normalized
        return cleaned

    @model_validator(mode="after")
    def validate_role_specific_fields(self) -> "ColumnEditItem":
        if self.semantic_role == "measure":
            if self.canonical_measure is None:
                allowed = ", ".join(CANONICAL_MEASURES)
                raise ValueError(f"canonical_measure is required for measure columns. Supported values: {allowed}.")
            if self.canonical_dimension is not None:
                raise ValueError("canonical_dimension is only allowed for dimension columns.")
            if self.unit is None:
                raise ValueError("unit is required for measure columns.")
            if not is_supported_unit_for_measure(self.canonical_measure, self.unit):
                raise ValueError(
                    f"unit {self.unit!r} is not supported for {self.canonical_measure}."
                )
        elif self.semantic_role == "dimension":
            if self.canonical_dimension is None:
                allowed = ", ".join(CANONICAL_DIMENSIONS)
                raise ValueError(
                    f"canonical_dimension is required for dimension columns. Supported values: {allowed}."
                )
            if self.canonical_measure is not None:
                raise ValueError("canonical_measure is only allowed for measure columns.")
            if self.unit is not None:
                raise ValueError("unit is only allowed for measure columns.")
        else:
            if self.canonical_measure is not None:
                raise ValueError("canonical_measure is only allowed for measure columns.")
            if self.canonical_dimension is not None:
                raise ValueError("canonical_dimension is only allowed for dimension columns.")
            if self.unit is not None:
                raise ValueError("unit is only allowed for measure columns.")

        return self


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[ColumnEditItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SheetManifestItemResponse(BaseModel):
    sheet_index: int = Field(ge=1)
    sheet_name: str
    row_count: int = Field(ge=0)
    max_column_count: int = Field(ge=0)
    non_empty_cell_count: int = Field(ge=0)
    detected_block_count: int = Field(ge=0)


class RawArtifactResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int = Field(ge=0)
    file_hash_sha256: str = Field(min_length=64, max_length=64)
    uploaded_at: datetime
    parser_version: str
    storage_type: str
    storage_path: str | None = None
    preview_generated_at: datetime | None = None
    sheet_manifest: list[SheetManifestItemResponse] = Field(default_factory=list)
    parse_warning_summary: list[str] = Field(default_factory=list)


class UploadCreateResponse(BaseModel):
    id: str
    status: Literal["preview_ready"]
    preview: PublicPreviewPayload
    raw_artifact: RawArtifactResponse | None = None


class UploadDetailResponse(BaseModel):
    id: str
    status: UploadStatus
    preview: PublicPreviewPayload
    raw_artifact: RawArtifactResponse | None = None


class UploadPreviewResponse(BaseModel):
    id: str
    preview: PublicPreviewPayload
    raw_artifact: RawArtifactResponse | None = None


class CommitResponse(BaseModel):
    id: str
    status: Literal["committed"]
    staging_rows: int = Field(ge=0)
    harmonized_rows: int = Field(ge=0)
