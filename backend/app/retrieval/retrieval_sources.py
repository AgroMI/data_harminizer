from __future__ import annotations

from typing import Any

from etl.quality_validation import INVALID_FLAGS, OUTLIER_RANGES
from etl.semantic_mapping import (
    CANONICAL_DATE,
    CANONICAL_DIMENSIONS,
    CANONICAL_MEASURES,
    DIMENSION_TOKEN_MAP,
    MEASURE_TOKEN_MAP,
)
from etl.unit_harmonization import CANONICAL_UNIT_BY_MEASURE, SUPPORTED_UNITS_BY_MEASURE

from backend.app.retrieval.retrieval_types import RetrievalDocument

CANONICAL_DIMENSION_DESCRIPTIONS: dict[str, str] = {
    "plot_id": "Stable plot or parcel identifier used as a canonical dimension.",
    "variety": "Canonical variety or cultivar dimension for grouping and filtering.",
    "treatment": "Canonical treatment dimension for fertilizer or management variants.",
    "location": "Canonical location or site dimension for field-level grouping.",
    "replicate": "Canonical replicate or block dimension for experimental design.",
}

CANONICAL_MEASURE_DESCRIPTIONS: dict[str, str] = {
    "yield": "Canonical production measure normalized to kg/ha.",
    "moisture": "Canonical moisture measure normalized to percent.",
    "plant_height": "Canonical plant height measure normalized to cm.",
}

VALIDATION_STATUS_DESCRIPTIONS: dict[str, str] = {
    "valid": "No quality flag is present on the observation.",
    "warning": "At least one non-blocking quality flag is present.",
    "invalid": "At least one blocking quality flag is present.",
}

QUALITY_FLAG_DESCRIPTIONS: dict[str, str] = {
    "missing_required_dimension": "No canonical dimension such as plot_id, variety, treatment or location was available.",
    "missing_observation_date": "The observation requires a date but none could be parsed.",
    "missing_unit": "The source unit or normalized unit is missing.",
    "missing_measure_value": "The measure value is missing after parsing.",
    "duplicate_candidate": "The canonical observation key appears more than once within the uploaded data.",
    "outlier_candidate": "The normalized value falls outside the configured deterministic range for the canonical measure.",
}


def build_raw_context_documents(upload_detail: dict[str, Any]) -> list[RetrievalDocument]:
    upload_session_id = str(upload_detail["id"])
    raw_artifact = upload_detail.get("raw_artifact") or {}
    preview = upload_detail.get("preview") or {}

    documents: list[RetrievalDocument] = []
    if raw_artifact:
        documents.append(_build_raw_artifact_document(raw_artifact=raw_artifact, upload_session_id=upload_session_id))
        documents.extend(
            _build_sheet_manifest_documents(
                sheet_manifest=raw_artifact.get("sheet_manifest", []),
                upload_session_id=upload_session_id,
            )
        )
        documents.extend(
            _build_parse_warning_documents(
                parse_warning_summary=raw_artifact.get("parse_warning_summary", []),
                upload_session_id=upload_session_id,
            )
        )

    documents.extend(
        _build_preview_block_documents(
            preview=preview,
            upload_session_id=upload_session_id,
        )
    )
    return documents


def build_schema_documents(query_metadata: dict[str, Any]) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = [
        RetrievalDocument(
            document_id="schema:overview",
            source_type="schema_doc",
            title="System schema overview",
            text=(
                "The harmonized read layer exposes canonical measures, canonical dimensions, normalized units, "
                "validation statuses and quality flags. Query endpoints are read-only and operate on harmonized observations."
            ),
            metadata={
                "canonical_date_field": CANONICAL_DATE,
                "canonical_dimensions": list(CANONICAL_DIMENSIONS),
                "canonical_measures": list(CANONICAL_MEASURES),
            },
        ),
        _build_query_metadata_document(query_metadata=query_metadata),
        _build_validation_overview_document(),
    ]

    for dimension in CANONICAL_DIMENSIONS:
        documents.append(
            RetrievalDocument(
                document_id=f"canonical:dimension:{dimension}",
                source_type="canonical_catalog",
                title=f"Canonical dimension: {dimension}",
                text=(
                    f"{CANONICAL_DIMENSION_DESCRIPTIONS[dimension]} "
                    f"Known matching tokens: {', '.join(DIMENSION_TOKEN_MAP[dimension])}."
                ),
                metadata={
                    "canonical_dimension": dimension,
                    "token_examples": list(DIMENSION_TOKEN_MAP[dimension]),
                },
            )
        )

    for measure in CANONICAL_MEASURES:
        documents.append(
            RetrievalDocument(
                document_id=f"canonical:measure:{measure}",
                source_type="canonical_catalog",
                title=f"Canonical measure: {measure}",
                text=(
                    f"{CANONICAL_MEASURE_DESCRIPTIONS[measure]} "
                    f"Known matching tokens: {', '.join(MEASURE_TOKEN_MAP[measure])}."
                ),
                metadata={
                    "canonical_measure": measure,
                    "token_examples": list(MEASURE_TOKEN_MAP[measure]),
                },
            )
        )
        documents.append(
            RetrievalDocument(
                document_id=f"units:{measure}",
                source_type="unit_doc",
                title=f"Unit model for {measure}",
                text=(
                    f"{measure} accepts source units {', '.join(SUPPORTED_UNITS_BY_MEASURE[measure])} "
                    f"and is normalized to {CANONICAL_UNIT_BY_MEASURE[measure]}."
                ),
                metadata={
                    "canonical_measure": measure,
                    "supported_units": list(SUPPORTED_UNITS_BY_MEASURE[measure]),
                    "canonical_unit": CANONICAL_UNIT_BY_MEASURE[measure],
                },
            )
        )

    for flag, description in QUALITY_FLAG_DESCRIPTIONS.items():
        documents.append(
            RetrievalDocument(
                document_id=f"validation:flag:{flag}",
                source_type="validation_doc",
                title=f"Validation flag: {flag}",
                text=description,
                metadata={
                    "quality_flag": flag,
                    "blocking": flag in INVALID_FLAGS,
                },
            )
        )

    return documents


def _build_raw_artifact_document(
    *,
    raw_artifact: dict[str, Any],
    upload_session_id: str,
) -> RetrievalDocument:
    file_name = str(raw_artifact.get("original_filename") or "unknown")
    return RetrievalDocument(
        document_id=f"upload:{upload_session_id}:artifact",
        source_type="raw_artifact",
        title=f"Raw artifact for upload {upload_session_id}",
        text=(
            f"Raw workbook {file_name} was uploaded with parser version {raw_artifact.get('parser_version')}. "
            f"MIME type: {raw_artifact.get('mime_type')}. File size: {raw_artifact.get('file_size_bytes')} bytes. "
            f"SHA-256: {raw_artifact.get('file_hash_sha256')}."
        ),
        metadata={
            "upload_session_id": upload_session_id,
            "original_filename": file_name,
            "parser_version": raw_artifact.get("parser_version"),
            "mime_type": raw_artifact.get("mime_type"),
            "file_size_bytes": raw_artifact.get("file_size_bytes"),
            "file_hash_sha256": raw_artifact.get("file_hash_sha256"),
            "preview_generated_at": raw_artifact.get("preview_generated_at"),
        },
        upload_session_id=upload_session_id,
    )


def _build_sheet_manifest_documents(
    *,
    sheet_manifest: list[dict[str, Any]],
    upload_session_id: str,
) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for sheet in sheet_manifest:
        sheet_name = str(sheet.get("sheet_name") or "unknown")
        documents.append(
            RetrievalDocument(
                document_id=f"upload:{upload_session_id}:sheet:{sheet_name}",
                source_type="sheet_manifest",
                title=f"Sheet manifest: {sheet_name}",
                text=(
                    f"Sheet {sheet_name} has {sheet.get('row_count', 0)} rows, "
                    f"{sheet.get('max_column_count', 0)} columns at maximum, "
                    f"{sheet.get('non_empty_cell_count', 0)} non-empty cells and "
                    f"{sheet.get('detected_block_count', 0)} detected blocks."
                ),
                metadata={
                    "upload_session_id": upload_session_id,
                    "sheet_name": sheet_name,
                    "sheet_index": sheet.get("sheet_index"),
                    "row_count": sheet.get("row_count"),
                    "max_column_count": sheet.get("max_column_count"),
                    "non_empty_cell_count": sheet.get("non_empty_cell_count"),
                    "detected_block_count": sheet.get("detected_block_count"),
                },
                upload_session_id=upload_session_id,
            )
        )
    return documents


def _build_parse_warning_documents(
    *,
    parse_warning_summary: list[str],
    upload_session_id: str,
) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for index, warning in enumerate(parse_warning_summary, start=1):
        warning_text = str(warning)
        documents.append(
            RetrievalDocument(
                document_id=f"upload:{upload_session_id}:warning:{index}",
                source_type="parse_warning",
                title=f"Parse warning {index} for upload {upload_session_id}",
                text=f"Parser warning: {warning_text}.",
                metadata={
                    "upload_session_id": upload_session_id,
                    "warning": warning_text,
                },
                upload_session_id=upload_session_id,
            )
        )
    return documents


def _build_preview_block_documents(
    *,
    preview: dict[str, Any],
    upload_session_id: str,
) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    blocks = preview.get("blocks", [])
    if not isinstance(blocks, list):
        return documents

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("block_id") or "unknown")
        sheet_name = str(block.get("sheet") or "unknown")
        headers = [str(value) for value in block.get("headers", []) if isinstance(value, str)]
        type_suggestions = block.get("type_suggestions", [])
        canonical_measures = sorted(
            {
                str(item.get("canonical_measure"))
                for item in type_suggestions
                if isinstance(item, dict) and item.get("canonical_measure")
            }
        )
        canonical_dimensions = sorted(
            {
                str(item.get("canonical_dimension"))
                for item in type_suggestions
                if isinstance(item, dict) and item.get("canonical_dimension")
            }
        )
        warning_codes = sorted(
            {
                str(code)
                for item in type_suggestions
                if isinstance(item, dict)
                for code in item.get("warnings", [])
                if isinstance(code, str)
            }
        )
        documents.append(
            RetrievalDocument(
                document_id=f"upload:{upload_session_id}:block:{block_id}",
                source_type="preview_block",
                title=f"Preview block {block_id} on {sheet_name}",
                text=(
                    f"Preview block {block_id} on sheet {sheet_name} covers range {block.get('range')}. "
                    f"Headers: {', '.join(headers) if headers else 'n/a'}. "
                    f"Canonical measures: {', '.join(canonical_measures) if canonical_measures else 'none'}. "
                    f"Canonical dimensions: {', '.join(canonical_dimensions) if canonical_dimensions else 'none'}. "
                    f"Warning codes: {', '.join(warning_codes) if warning_codes else 'none'}."
                ),
                metadata={
                    "upload_session_id": upload_session_id,
                    "block_id": block_id,
                    "sheet": sheet_name,
                    "range": block.get("range"),
                    "headers": headers,
                    "canonical_measures": canonical_measures,
                    "canonical_dimensions": canonical_dimensions,
                    "warning_codes": warning_codes,
                },
                upload_session_id=upload_session_id,
            )
        )
    return documents


def _build_query_metadata_document(query_metadata: dict[str, Any]) -> RetrievalDocument:
    return RetrievalDocument(
        document_id="query:metadata",
        source_type="query_metadata",
        title="Harmonized query metadata",
        text=(
            f"Supported filters: {', '.join(query_metadata.get('supported_filters', []))}. "
            f"Supported group by values: {', '.join(query_metadata.get('supported_group_bys', []))}. "
            f"Supported metrics: {', '.join(query_metadata.get('supported_metrics', []))}. "
            f"Available variables: {', '.join(query_metadata.get('available_variables', [])) or 'none'}. "
            f"Available normalized units: {', '.join(query_metadata.get('available_normalized_units', [])) or 'none'}."
        ),
        metadata={
            "supported_filters": list(query_metadata.get("supported_filters", [])),
            "supported_group_bys": list(query_metadata.get("supported_group_bys", [])),
            "supported_metrics": list(query_metadata.get("supported_metrics", [])),
            "available_variables": list(query_metadata.get("available_variables", [])),
            "available_normalized_units": list(query_metadata.get("available_normalized_units", [])),
            "available_varieties": list(query_metadata.get("available_varieties", [])),
            "available_locations": list(query_metadata.get("available_locations", [])),
            "available_treatments": list(query_metadata.get("available_treatments", [])),
            "available_plot_ids": list(query_metadata.get("available_plot_ids", [])),
        },
    )


def _build_validation_overview_document() -> RetrievalDocument:
    invalid_flag_list = ", ".join(sorted(INVALID_FLAGS))
    outlier_parts = [
        f"{measure}:{bounds[0]}..{bounds[1]}"
        for measure, bounds in OUTLIER_RANGES.items()
    ]
    status_text = " ".join(
        f"{status}: {description}"
        for status, description in VALIDATION_STATUS_DESCRIPTIONS.items()
    )
    return RetrievalDocument(
        document_id="validation:overview",
        source_type="validation_doc",
        title="Validation and quality overview",
        text=(
            f"{status_text} Blocking flags: {invalid_flag_list}. "
            f"Outlier ranges: {', '.join(outlier_parts)}."
        ),
        metadata={
            "validation_statuses": list(VALIDATION_STATUS_DESCRIPTIONS.keys()),
            "invalid_flags": sorted(INVALID_FLAGS),
            "outlier_ranges": [f"{measure}:{lower}-{upper}" for measure, (lower, upper) in OUTLIER_RANGES.items()],
        },
    )
