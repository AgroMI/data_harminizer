from __future__ import annotations

from etl.preview_schema import build_preview, extract_table_from_block_cells
from etl.type_inference import detect_date_issues, infer_column_types


def test_extract_table_uses_header_row_when_textual() -> None:
    table = extract_table_from_block_cells(
        [
            ["Date", "Yield"],
            ["2025-01-01", 12.4],
            ["2025-01-02", 13.1],
        ]
    )

    assert table["header_in_first_row"] is True
    assert table["headers"] == ["date", "yield"]
    assert table["data_rows"][0]["date"] == "2025-01-01"


def test_infer_column_types_detects_numeric_and_date() -> None:
    headers = ["date", "yield", "note"]
    rows = [
        {"date": "2025-01-01", "yield": 10.0, "note": "A"},
        {"date": "2025-01-02", "yield": 11.2, "note": "B"},
        {"date": "2025-01-03", "yield": "12.8", "note": "C"},
    ]

    suggestions = infer_column_types(headers, rows)
    suggestion_by_column = {item["column"]: item["suggested"] for item in suggestions}

    assert suggestion_by_column["date"] == "date"
    assert suggestion_by_column["yield"] == "numeric"
    assert suggestion_by_column["note"] == "text"


def test_detect_date_issues_reports_unparseable_examples() -> None:
    headers = ["date", "value"]
    rows = [
        {"date": "2025-01-01", "value": 1},
        {"date": "not-a-date", "value": 2},
        {"date": "2025-01-03", "value": 3},
    ]
    type_suggestions = [
        {
            "column": "date",
            "suggested": "date",
            "type_override": None,
            "semantic_role": "date",
            "canonical_measure": None,
            "canonical_dimension": None,
            "unit": None,
            "warnings": [],
        },
        {
            "column": "value",
            "suggested": "numeric",
            "type_override": None,
            "semantic_role": "measure",
            "canonical_measure": "yield",
            "canonical_dimension": None,
            "unit": None,
            "warnings": [],
        },
    ]

    issues = detect_date_issues(headers, rows, type_suggestions)

    assert len(issues) == 1
    assert issues[0]["column"] == "date"
    assert "not-a-date" in issues[0]["example_values"]


def test_extract_table_skips_sparse_preamble_and_combines_header_rows() -> None:
    table = extract_table_from_block_cells(
        [
            [None, None, "Parcellatermes t/ha.", None],
            [None, "N 0", "N 40", "N 80"],
            [None, "A", "B", "C"],
            ["I.", 4.05, 6.21, 5.88],
            ["II.", 4.24, 5.30, 6.50],
            ["III.", 5.59, 6.29, 6.51],
        ]
    )

    assert table["header_in_first_row"] is False
    assert table["header_row_count"] == 2
    assert table["data_row_start_index"] == 3
    assert table["headers"] == ["column_1", "n_0_a", "n_40_b", "n_80_c"]
    assert table["data_rows"][0]["column_1"] == "I."
    assert table["data_rows"][0]["n_0_a"] == 4.05


def test_build_preview_marks_trimmed_numeric_columns_as_measures() -> None:
    preview = build_preview(
        file_name="demo.xlsx",
        block_records=[
            {
                "block_id": "S1_B1",
                "sheet_name": "Sheet1",
                "row_start": 1,
                "row_end": 6,
                "col_start": 1,
                "col_end": 4,
                "row_count": 6,
                "col_count": 4,
                "rows": [
                    [None, None, "Parcellatermes t/ha.", None],
                    [None, "N 0", "N 40", "N 80"],
                    [None, "A", "B", "C"],
                    ["I.", 4.05, 6.21, 5.88],
                    ["II.", 4.24, 5.30, 6.50],
                    ["III.", 5.59, 6.29, 6.51],
                ],
            }
        ],
    )

    block = preview["blocks"][0]
    columns = {item["column"]: item for item in block["type_suggestions"]}

    assert block["headers"] == ["column_1", "n_0_a", "n_40_b", "n_80_c"]
    assert block["sample_rows"][0]["column_1"] == "I."
    assert columns["column_1"]["semantic_role"] == "dimension"
    assert columns["n_0_a"]["suggested"] == "numeric"
    assert columns["n_0_a"]["semantic_role"] == "measure"
    assert columns["n_40_b"]["semantic_role"] == "measure"
