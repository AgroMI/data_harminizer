from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from backend.app.db import get_conn
from backend.app.schemas import AggregationGroupBy, AggregationMetric
from etl.semantic_mapping import CANONICAL_MEASURES
from etl.types import CanonicalMeasure, CanonicalUnit, QualityFlag, ValidationStatus

LIST_HARMONIZED_OBSERVATIONS_SQL = """
SELECT
    upload_session_id::text AS upload_session_id,
    observation_date,
    plot_id,
    variety,
    treatment,
    location,
    variable,
    value::double precision AS value,
    unit,
    normalized_value::double precision AS normalized_value,
    normalized_unit,
    validation_status,
    quality_flags,
    source_sheet,
    source_row_index,
    source_column
FROM harmonized.observations
"""

QUERY_METADATA_VARIABLES_SQL = """
SELECT DISTINCT variable
FROM harmonized.observations
WHERE variable IS NOT NULL
ORDER BY variable
"""

QUERY_METADATA_UNITS_SQL = """
SELECT DISTINCT normalized_unit
FROM harmonized.observations
WHERE normalized_unit IS NOT NULL
ORDER BY normalized_unit
"""

QUERY_METADATA_VARIETIES_SQL = """
SELECT DISTINCT variety
FROM harmonized.observations
WHERE variety IS NOT NULL
ORDER BY variety
"""

QUERY_METADATA_LOCATIONS_SQL = """
SELECT DISTINCT location
FROM harmonized.observations
WHERE location IS NOT NULL
ORDER BY location
"""

QUERY_METADATA_TREATMENTS_SQL = """
SELECT DISTINCT treatment
FROM harmonized.observations
WHERE treatment IS NOT NULL
ORDER BY treatment
"""

QUERY_METADATA_PLOT_IDS_SQL = """
SELECT DISTINCT plot_id
FROM harmonized.observations
WHERE plot_id IS NOT NULL
ORDER BY plot_id
"""

QUERY_METADATA_STATUSES_SQL = """
SELECT DISTINCT validation_status
FROM harmonized.observations
WHERE validation_status IS NOT NULL
ORDER BY validation_status
"""

QUERY_METADATA_FLAGS_SQL = """
SELECT DISTINCT jsonb_array_elements_text(quality_flags) AS quality_flag
FROM harmonized.observations
WHERE quality_flags <> '[]'::jsonb
ORDER BY quality_flag
"""

GROUP_BY_COLUMN_MAP: dict[AggregationGroupBy, str] = {
    "variety": "variety",
    "treatment": "treatment",
    "location": "location",
    "validation_status": "validation_status",
}

SUPPORTED_FILTERS: tuple[str, ...] = (
    "upload_session_id",
    "variable",
    "variety",
    "location",
    "treatment",
    "plot_id",
    "observation_date_from",
    "observation_date_to",
    "validation_status",
    "quality_flag",
    "normalized_unit",
)
SUPPORTED_GROUP_BYS: tuple[AggregationGroupBy, ...] = (
    "variety",
    "treatment",
    "location",
    "validation_status",
)
SUPPORTED_METRICS: tuple[AggregationMetric, ...] = (
    "avg_normalized_value",
    "count",
)
SUPPORTED_VALIDATION_STATUSES: tuple[ValidationStatus, ...] = (
    "valid",
    "warning",
    "invalid",
)
SUPPORTED_QUALITY_FLAGS: tuple[QualityFlag, ...] = (
    "missing_required_dimension",
    "missing_observation_date",
    "missing_unit",
    "missing_measure_value",
    "duplicate_candidate",
    "outlier_candidate",
)


@dataclass(frozen=True, slots=True)
class HarmonizedObservationFilters:
    upload_session_id: str | None = None
    variable: CanonicalMeasure | None = None
    variety: str | None = None
    location: str | None = None
    treatment: str | None = None
    plot_id: str | None = None
    observation_date_from: date | None = None
    observation_date_to: date | None = None
    validation_status: ValidationStatus | None = None
    quality_flag: QualityFlag | None = None
    normalized_unit: CanonicalUnit | None = None


def list_harmonized_observations(
    *,
    limit: int,
    filters: HarmonizedObservationFilters,
) -> dict[str, Any]:
    sql = LIST_HARMONIZED_OBSERVATIONS_SQL
    where_clauses, params = _build_where_clauses(filters=filters)

    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"

    sql = (
        f"{sql} ORDER BY observation_date NULLS LAST, variable, plot_id NULLS LAST, "
        "source_sheet, source_row_index, source_column LIMIT %s"
    )
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    return {"items": rows, "count": len(rows)}


def aggregate_harmonized_observations(
    *,
    group_by: AggregationGroupBy,
    metric: AggregationMetric,
    filters: HarmonizedObservationFilters,
    include_invalid: bool,
) -> dict[str, Any]:
    if metric == "avg_normalized_value" and group_by == "validation_status":
        raise HTTPException(
            status_code=422,
            detail="avg_normalized_value is only supported for group_by variety, treatment or location.",
        )

    group_column = GROUP_BY_COLUMN_MAP[group_by]
    where_clauses, params = _build_where_clauses(filters=filters)

    if metric == "avg_normalized_value":
        where_clauses.append("normalized_value IS NOT NULL")
        if filters.variable is None:
            raise HTTPException(
                status_code=422,
                detail="variable is required for avg_normalized_value aggregations.",
            )

    if filters.validation_status is None and not include_invalid and group_by != "validation_status":
        where_clauses.append("validation_status <> 'invalid'")

    if metric == "avg_normalized_value":
        sql = f"""
        SELECT
            {group_column} AS group_value,
            avg(normalized_value)::double precision AS metric_value,
            count(*)::integer AS record_count,
            max(normalized_unit) AS normalized_unit
        FROM harmonized.observations
        """
    else:
        sql = f"""
        SELECT
            {group_column} AS group_value,
            count(*)::integer AS metric_value,
            count(*)::integer AS record_count,
            NULL::text AS normalized_unit
        FROM harmonized.observations
        """

    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"

    sql = f"{sql} GROUP BY {group_column} ORDER BY {group_column} NULLS LAST"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    return {
        "group_by": group_by,
        "metric": metric,
        "include_invalid": include_invalid,
        "items": rows,
        "count": len(rows),
    }


def get_harmonized_query_metadata() -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            variables = _fetch_distinct_values(cur, QUERY_METADATA_VARIABLES_SQL, "variable")
            normalized_units = _fetch_distinct_values(cur, QUERY_METADATA_UNITS_SQL, "normalized_unit")
            varieties = _fetch_distinct_values(cur, QUERY_METADATA_VARIETIES_SQL, "variety")
            locations = _fetch_distinct_values(cur, QUERY_METADATA_LOCATIONS_SQL, "location")
            treatments = _fetch_distinct_values(cur, QUERY_METADATA_TREATMENTS_SQL, "treatment")
            plot_ids = _fetch_distinct_values(cur, QUERY_METADATA_PLOT_IDS_SQL, "plot_id")
            validation_statuses = _fetch_distinct_values(
                cur,
                QUERY_METADATA_STATUSES_SQL,
                "validation_status",
            )
            quality_flags = _fetch_distinct_values(cur, QUERY_METADATA_FLAGS_SQL, "quality_flag")

    return {
        "supported_filters": list(SUPPORTED_FILTERS),
        "supported_group_bys": list(SUPPORTED_GROUP_BYS),
        "supported_metrics": list(SUPPORTED_METRICS),
        "supported_validation_statuses": list(SUPPORTED_VALIDATION_STATUSES),
        "supported_quality_flags": list(SUPPORTED_QUALITY_FLAGS),
        "available_variables": variables,
        "available_normalized_units": normalized_units,
        "available_varieties": varieties,
        "available_locations": locations,
        "available_treatments": treatments,
        "available_plot_ids": plot_ids,
        "available_validation_statuses": validation_statuses,
        "available_quality_flags": quality_flags,
        "aggregations_exclude_invalid_by_default": True,
    }


def _build_where_clauses(
    *,
    filters: HarmonizedObservationFilters,
) -> tuple[list[str], list[Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if filters.upload_session_id:
        where_clauses.append("upload_session_id = %s")
        params.append(filters.upload_session_id)
    if filters.variable:
        where_clauses.append("variable = %s")
        params.append(filters.variable)
    if filters.variety:
        where_clauses.append("variety = %s")
        params.append(filters.variety)
    if filters.location:
        where_clauses.append("location = %s")
        params.append(filters.location)
    if filters.treatment:
        where_clauses.append("treatment = %s")
        params.append(filters.treatment)
    if filters.plot_id:
        where_clauses.append("plot_id = %s")
        params.append(filters.plot_id)
    if filters.observation_date_from:
        where_clauses.append("observation_date >= %s")
        params.append(filters.observation_date_from)
    if filters.observation_date_to:
        where_clauses.append("observation_date <= %s")
        params.append(filters.observation_date_to)
    if filters.validation_status:
        where_clauses.append("validation_status = %s")
        params.append(filters.validation_status)
    if filters.quality_flag:
        where_clauses.append("quality_flags @> %s")
        params.append(Jsonb([filters.quality_flag]))
    if filters.normalized_unit:
        where_clauses.append("normalized_unit = %s")
        params.append(filters.normalized_unit)

    return where_clauses, params


def _fetch_distinct_values(cur: Any, sql: str, column_name: str) -> list[Any]:
    cur.execute(sql)
    rows = cur.fetchall()
    return [row[column_name] for row in rows if row.get(column_name) is not None]
