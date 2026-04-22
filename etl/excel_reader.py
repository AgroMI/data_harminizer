from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import xlrd
from openpyxl import load_workbook

from etl.types import WorkbookSheet

WorkbookReader = Callable[[bytes], list[WorkbookSheet]]


def _normalize_row(row: tuple[Any, ...] | list[Any]) -> list[Any]:
    return list(row)


def _read_workbook_openpyxl(file_bytes: bytes) -> list[WorkbookSheet]:
    workbook = load_workbook(filename=BytesIO(file_bytes), data_only=True)
    sheets: list[WorkbookSheet] = []

    for sheet_index, worksheet in enumerate(workbook.worksheets, start=1):
        rows = [_normalize_row(row) for row in worksheet.iter_rows(values_only=True)]
        sheets.append(
            {
                "sheet_index": sheet_index,
                "sheet_name": worksheet.title,
                "rows": rows,
            }
        )

    workbook.close()
    return sheets


def _convert_xlrd_cell(cell: xlrd.sheet.Cell, datemode: int) -> Any:
    if cell.ctype == xlrd.XL_CELL_DATE:
        # Keep date/datetime values typed for downstream inference.
        return xlrd.xldate.xldate_as_datetime(cell.value, datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype in {xlrd.XL_CELL_ERROR, xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
        return None
    return cell.value


def _read_workbook_xlrd(file_bytes: bytes) -> list[WorkbookSheet]:
    workbook = xlrd.open_workbook(file_contents=file_bytes)
    sheets: list[WorkbookSheet] = []

    for sheet_index, sheet in enumerate(workbook.sheets(), start=1):
        rows: list[list[Any]] = []

        for row_idx in range(sheet.nrows):
            rows.append(
                [
                    _convert_xlrd_cell(sheet.cell(row_idx, col_idx), workbook.datemode)
                    for col_idx in range(sheet.ncols)
                ]
            )

        sheets.append(
            {
                "sheet_index": sheet_index,
                "sheet_name": sheet.name,
                "rows": rows,
            }
        )

    return sheets


def _ordered_readers(filename: str | None) -> tuple[WorkbookReader, WorkbookReader]:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".xls":
        return _read_workbook_xlrd, _read_workbook_openpyxl
    return _read_workbook_openpyxl, _read_workbook_xlrd


def read_excel_workbook(file_bytes: bytes, filename: str | None = None) -> list[WorkbookSheet]:
    errors: list[Exception] = []

    for reader in _ordered_readers(filename):
        try:
            return reader(file_bytes)
        except Exception as exc:  # pragma: no cover - fallback chain
            errors.append(exc)

    raise RuntimeError("Could not parse Excel workbook as .xlsx or .xls") from (
        errors[-1] if errors else None
    )
