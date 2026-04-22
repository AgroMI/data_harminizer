from __future__ import annotations

from datetime import datetime, timezone

from etl.block_detector import detect_blocks_with_positions
from etl.excel_reader import read_excel_workbook
from etl.preview_schema import build_preview
from etl.types import BlockRecord, ParsedUploadSource, PreviewPayload, SheetManifestItem

PARSER_VERSION = "excel_preview_parser_v2"


def _non_empty_cell_count(rows: list[list[object]]) -> int:
    count = 0
    for row in rows:
        for value in row:
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            count += 1
    return count


def _sheet_manifest_item(
    *,
    sheet_index: int,
    sheet_name: str,
    rows: list[list[object]],
    detected_block_count: int,
) -> SheetManifestItem:
    return {
        "sheet_index": sheet_index,
        "sheet_name": sheet_name,
        "row_count": len(rows),
        "max_column_count": max((len(row) for row in rows), default=0),
        "non_empty_cell_count": _non_empty_cell_count(rows),
        "detected_block_count": detected_block_count,
    }


def _parse_warning_summary(sheet_manifest: list[SheetManifestItem]) -> list[str]:
    warnings: list[str] = []
    for item in sheet_manifest:
        if item["row_count"] == 0:
            warnings.append(f"empty_sheet:{item['sheet_name']}")
        elif item["detected_block_count"] == 0:
            warnings.append(f"no_blocks_detected:{item['sheet_name']}")
    return warnings


def parse_upload_source(file_bytes: bytes, filename: str) -> ParsedUploadSource:
    try:
        workbook = read_excel_workbook(file_bytes, filename=filename)
    except Exception as exc:  # pragma: no cover - minimal scaffold safeguard
        raise ValueError("Could not parse Excel file. Ensure it is a valid .xlsx or .xls file.") from exc

    block_records: list[BlockRecord] = []
    sheet_manifest: list[SheetManifestItem] = []

    for sheet in workbook:
        sheet_index = sheet["sheet_index"]
        sheet_name = sheet["sheet_name"]
        rows = sheet["rows"]
        detected_blocks = detect_blocks_with_positions(rows)

        sheet_manifest.append(
            _sheet_manifest_item(
                sheet_index=sheet_index,
                sheet_name=sheet_name,
                rows=rows,
                detected_block_count=len(detected_blocks),
            )
        )

        for block_number, block in enumerate(detected_blocks, start=1):
            block_records.append(
                {
                    "block_id": f"S{sheet_index}_B{block_number}",
                    "sheet_name": sheet_name,
                    "row_start": block["row_start"],
                    "row_end": block["row_end"],
                    "col_start": block["col_start"],
                    "col_end": block["col_end"],
                    "row_count": block["row_count"],
                    "col_count": block["col_count"],
                    "rows": block["rows"],
                }
            )

    return {
        "preview": build_preview(file_name=filename, block_records=block_records),
        "parser_version": PARSER_VERSION,
        "sheet_manifest": sheet_manifest,
        "preview_generated_at": datetime.now(timezone.utc),
        "parse_warning_summary": _parse_warning_summary(sheet_manifest),
    }


def parse_preview(file_bytes: bytes, filename: str) -> PreviewPayload:
    return parse_upload_source(file_bytes=file_bytes, filename=filename)["preview"]
