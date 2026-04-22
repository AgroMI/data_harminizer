from __future__ import annotations

from typing import Any

from etl.types import DataRow


def normalize_header(raw_header: Any, index: int) -> str:
    if raw_header is None:
        return f"column_{index + 1}"

    text = str(raw_header).strip().lower().replace(" ", "_")
    return text or f"column_{index + 1}"


def make_unique_headers(headers: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    unique: list[str] = []

    for header in headers:
        count = counts.get(header, 0) + 1
        counts[header] = count
        unique.append(header if count == 1 else f"{header}_{count}")

    return unique


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def rows_to_dicts(headers: list[str], rows: list[list[Any]]) -> list[DataRow]:
    items: list[DataRow] = []

    for row in rows:
        item = {
            header: row[index] if index < len(row) else None
            for index, header in enumerate(headers)
        }
        items.append(item)

    return items
