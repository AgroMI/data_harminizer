from __future__ import annotations

from backend.app.services.preview_service import parse_upload_source
from etl.excel_reader import read_tabular_source


def test_read_tabular_source_reads_comma_csv() -> None:
    sheets = read_tabular_source(
        b"date,plot_id,yield\n2024-07-01,P1,6.2\n",
        filename="observations.csv",
    )

    assert sheets == [
        {
            "sheet_index": 1,
            "sheet_name": "observations",
            "rows": [
                ["date", "plot_id", "yield"],
                ["2024-07-01", "P1", "6.2"],
            ],
        }
    ]


def test_read_tabular_source_detects_semicolon_csv() -> None:
    sheets = read_tabular_source(
        b"date;plot_id;yield\n2024-07-01;P1;6.2\n",
        filename="observations.csv",
    )

    assert sheets[0]["rows"][0] == ["date", "plot_id", "yield"]
    assert sheets[0]["rows"][1] == ["2024-07-01", "P1", "6.2"]


def test_read_tabular_source_reads_tsv() -> None:
    sheets = read_tabular_source(
        b"date\tplot_id\tyield\n2024-07-01\tP1\t6.2\n",
        filename="observations.tsv",
    )

    assert sheets[0]["rows"][0] == ["date", "plot_id", "yield"]
    assert sheets[0]["rows"][1] == ["2024-07-01", "P1", "6.2"]


def test_read_tabular_source_handles_cp1250_csv() -> None:
    content = "dátum;fajta;yield\n2024-07-01;Őszi búza;6.2\n".encode("cp1250")
    sheets = read_tabular_source(content, filename="koltay.csv")

    assert sheets[0]["rows"][0] == ["dátum", "fajta", "yield"]
    assert sheets[0]["rows"][1] == ["2024-07-01", "Őszi búza", "6.2"]


def test_parse_upload_source_builds_preview_from_csv() -> None:
    parsed = parse_upload_source(
        (
            b"date,plot_id,yield\n"
            b"2024-07-01,P1,6.2\n"
            b"2024-07-02,P2,6.8\n"
            b"2024-07-03,P3,7.1\n"
            b"2024-07-04,P4,6.9\n"
            b"2024-07-05,P5,7.4\n"
            b"2024-07-06,P6,7.0\n"
            b"2024-07-07,P7,7.5\n"
        ),
        filename="plot_data.csv",
    )

    preview = parsed["preview"]
    assert parsed["parser_version"] == "tabular_preview_parser_v1"
    assert preview["file_name"] == "plot_data.csv"
    assert preview["block_count"] == 1
    assert preview["blocks"][0]["headers"] == ["date", "plot_id", "yield"]
