from __future__ import annotations

from backend.app.text_to_sql.models import GeneratedSql, QueryPlan
from backend.app.text_to_sql.sql_validator import validate_generated_sql


def test_sql_validator_accepts_safe_generated_query() -> None:
    validation = validate_generated_sql(
        sql_bundle=GeneratedSql(
            sql=(
                "SELECT group_value, metric_value, record_count, normalized_unit "
                "FROM safe.harmonized_observations_v1 LIMIT %s"
            ),
            parameters=[10],
            relation_names=["safe.harmonized_observations_v1"],
            projected_columns=["group_value", "metric_value", "record_count", "normalized_unit"],
        ),
        plan=QueryPlan(
            status="supported",
            intent="select_records",
            source_relation="safe.harmonized_observations_v1",
            result_type="records",
        ),
    )

    assert validation.valid is True


def test_sql_validator_rejects_non_whitelisted_relation() -> None:
    validation = validate_generated_sql(
        sql_bundle=GeneratedSql(
            sql="SELECT * FROM harmonized.observations LIMIT %s",
            parameters=[10],
            relation_names=["harmonized.observations"],
            projected_columns=["*"],
        ),
        plan=None,
    )

    assert validation.valid is False
    assert {item.code for item in validation.issues} >= {"relation_not_whitelisted", "identifier_not_allowed"}


def test_sql_validator_rejects_missing_limit() -> None:
    validation = validate_generated_sql(
        sql_bundle=GeneratedSql(
            sql="SELECT * FROM safe.harmonized_observations_v1",
            parameters=[],
            relation_names=["safe.harmonized_observations_v1"],
            projected_columns=["*"],
        ),
        plan=None,
    )

    assert validation.valid is False
    assert {item.code for item in validation.issues} >= {"missing_limit", "missing_limit_parameter"}
