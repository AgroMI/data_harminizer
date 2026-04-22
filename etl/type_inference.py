from datetime import date, datetime
from typing import Any

from etl.table_utils import is_missing
from etl.types import DataRow, DateIssueItem, TypeSuggestionItem

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
)

NUMERIC_THRESHOLD = 0.8
DATE_THRESHOLD = 0.6
MAX_DATE_ISSUE_EXAMPLES = 5


def parse_date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


def is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return True

    if not isinstance(value, str):
        return False

    cleaned = value.strip()
    if not cleaned:
        return False

    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def to_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def infer_column_types(
    headers: list[str],
    data_rows: list[DataRow],
    *,
    row_limit: int = 200,
) -> list[TypeSuggestionItem]:
    suggestions: list[TypeSuggestionItem] = []
    limited_rows = data_rows[:row_limit]

    for header in headers:
        values = [
            row.get(header)
            for row in limited_rows
            if not is_missing(row.get(header))
        ]

        if not values:
            suggested: TypeSuggestionItem["suggested"] = "text"
        else:
            numeric_ratio = sum(1 for value in values if is_numeric_value(value)) / len(values)
            date_ratio = sum(1 for value in values if parse_date_value(value) is not None) / len(values)

            if numeric_ratio >= NUMERIC_THRESHOLD:
                suggested = "numeric"
            elif date_ratio >= DATE_THRESHOLD:
                suggested = "date"
            else:
                suggested = "text"

        suggestions.append(
            {
                "column": header,
                "suggested": suggested,
                "type_override": None,
                "semantic_role": "ignore",
                "canonical_measure": None,
                "canonical_dimension": None,
                "unit": None,
                "warnings": [],
            }
        )

    return suggestions


def detect_date_issues(
    headers: list[str],
    data_rows: list[DataRow],
    type_suggestions: list[TypeSuggestionItem],
    *,
    row_limit: int = 200,
) -> list[DateIssueItem]:
    suggested_date_columns = [
        suggestion["column"]
        for suggestion in type_suggestions
        if suggestion["suggested"] == "date"
    ]
    limited_rows = data_rows[:row_limit]
    issues: list[DateIssueItem] = []

    for column in suggested_date_columns:
        if column not in headers:
            continue

        bad_examples: list[str] = []
        for row in limited_rows:
            value = row.get(column)
            if is_missing(value) or parse_date_value(value) is not None:
                continue

            rendered = str(value)
            if rendered in bad_examples:
                continue

            bad_examples.append(rendered)
            if len(bad_examples) >= MAX_DATE_ISSUE_EXAMPLES:
                break

        if not bad_examples:
            continue

        issues.append(
            {
                "column": column,
                "issue": "mixed_or_unparseable_dates",
                "example_values": bad_examples,
            }
        )

    return issues
