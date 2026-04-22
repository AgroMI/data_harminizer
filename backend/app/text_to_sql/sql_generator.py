from backend.app.text_to_sql.catalog import SAFE_PROJECTION_COLUMNS, SAFE_RELATION_NAME
from backend.app.text_to_sql.models import GeneratedSql, QueryPlan


def generate_sql_from_plan(plan: QueryPlan) -> GeneratedSql:
    if not plan.supported:
        raise ValueError("Cannot generate SQL: the planner marked this query plan as unsupported — check the question for unsupported intent patterns.")

    if plan.intent == "select_records":
        return _generate_record_sql(plan)
    if plan.intent == "aggregate":
        return _generate_aggregate_sql(plan)
    raise ValueError(f"Unsupported query plan intent for SQL generation: {plan.intent}.")


def _generate_record_sql(plan: QueryPlan) -> GeneratedSql:
    where_clauses, parameters = _build_where_clauses(plan)
    projection = ", ".join(SAFE_PROJECTION_COLUMNS)
    sql = f"SELECT {projection} FROM {SAFE_RELATION_NAME}"
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    sql = f"{sql} ORDER BY observation_date NULLS LAST, variable ASC, plot_id NULLS LAST LIMIT %s"
    parameters.append(plan.limit)
    return GeneratedSql(
        sql=sql,
        parameters=parameters,
        relation_names=[SAFE_RELATION_NAME],
        projected_columns=list(SAFE_PROJECTION_COLUMNS),
    )


def _generate_aggregate_sql(plan: QueryPlan) -> GeneratedSql:
    aggregation = plan.aggregations[0]
    where_clauses, parameters = _build_where_clauses(plan)
    group_field = plan.grouping[0] if plan.grouping else None

    if aggregation.function == "avg":
        where_clauses.append("normalized_value IS NOT NULL")
        if not _has_filter(plan, "validation_status"):
            where_clauses.append("validation_status <> 'invalid'")
        metric_sql = "avg(normalized_value)::double precision AS metric_value"
        unit_sql = "max(normalized_unit) AS normalized_unit"
    else:
        metric_sql = "count(*)::integer AS metric_value"
        unit_sql = "NULL::text AS normalized_unit"

    group_expr = f"{group_field} AS group_value" if group_field is not None else "NULL::text AS group_value"
    sql = (
        f"SELECT {group_expr}, {metric_sql}, count(*)::integer AS record_count, {unit_sql} "
        f"FROM {SAFE_RELATION_NAME}"
    )
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    if group_field is not None:
        sql = f"{sql} GROUP BY {group_field}"

    order_sql = _build_order_by(plan)
    if order_sql:
        sql = f"{sql} ORDER BY {order_sql}"
    sql = f"{sql} LIMIT %s"
    parameters.append(plan.limit)
    return GeneratedSql(
        sql=sql,
        parameters=parameters,
        relation_names=[SAFE_RELATION_NAME],
        projected_columns=["group_value", "metric_value", "record_count", "normalized_unit"],
    )


def _build_where_clauses(plan: QueryPlan) -> tuple[list[str], list[object]]:
    where_clauses: list[str] = []
    parameters: list[object] = []
    for filter_item in plan.filters:
        if filter_item.operator == "eq":
            where_clauses.append(f"{filter_item.field_name} = %s")
            parameters.append(filter_item.value)
        elif filter_item.operator == "gte":
            where_clauses.append(f"{filter_item.field_name} >= %s")
            parameters.append(filter_item.value)
        elif filter_item.operator == "lte":
            where_clauses.append(f"{filter_item.field_name} <= %s")
            parameters.append(filter_item.value)
        elif filter_item.operator == "in":
            filter_values = list(filter_item.value) if isinstance(filter_item.value, list) else [filter_item.value]
            placeholders = ", ".join(["%s"] * len(filter_values))
            where_clauses.append(f"{filter_item.field_name} IN ({placeholders})")
            parameters.extend(filter_values)
    return where_clauses, parameters


def _build_order_by(plan: QueryPlan) -> str:
    if not plan.ordering:
        if plan.grouping:
            return f"{plan.grouping[0]} ASC NULLS LAST"
        return "metric_value DESC"
    return ", ".join(
        f"{item.field_name} {item.direction.upper()} NULLS LAST"
        for item in plan.ordering
    )


def _has_filter(plan: QueryPlan, field_name: str) -> bool:
    return any(item.field_name == field_name for item in plan.filters)
