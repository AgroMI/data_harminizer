from __future__ import annotations

from etl.table_utils import is_missing
from etl.types import DataRow, MissingByColumnItem


def compute_missing_by_column(
    headers: list[str],
    data_rows: list[DataRow],
) -> list[MissingByColumnItem]:
    total = len(data_rows)
    summary: list[MissingByColumnItem] = []

    for header in headers:
        missing = sum(1 for row in data_rows if is_missing(row.get(header)))
        ratio = round((missing / total), 3) if total else 0.0
        summary.append(
            {
                "column": header,
                "missing": missing,
                "total": total,
                "ratio": ratio,
            }
        )

    return summary
