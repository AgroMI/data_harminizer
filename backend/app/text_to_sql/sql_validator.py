import re

from backend.app.text_to_sql.catalog import MAX_RECORD_LIMIT, SAFE_FILTER_FIELDS, SAFE_GROUP_FIELDS, SAFE_RELATION_NAME
from backend.app.text_to_sql.models import GeneratedSql, QueryPlan, SqlValidationIssue, SqlValidationResult

FORBIDDEN_SQL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("semicolon", r";"),
    ("comment", r"--|/\*|\*/"),
    ("ddl_or_dml", r"\b(insert|update|delete|alter|drop|truncate|grant|revoke|create)\b"),
    ("system_schema", r"\b(pg_catalog|information_schema)\b"),
    ("join", r"\bjoin\b"),
)

SQL_KEYWORDS: set[str] = {
    "select",
    "from",
    "where",
    "and",
    "or",
    "is",
    "not",
    "group",
    "by",
    "order",
    "limit",
    "as",
    "nulls",
    "last",
    "asc",
    "desc",
    "null",
    "text",
    "double",
    "precision",
    "integer",
    "avg",
    "count",
    "max",
    "in",
    "ilike",
    "like",
    "safe",
    "harmonized_observations_v1",
    "group_value",
    "metric_value",
    "record_count",
}

ALLOWED_IDENTIFIERS: set[str] = {
    "upload_session_id",
    "observation_date",
    "plot_id",
    "variety",
    "treatment",
    "location",
    "variable",
    "value",
    "unit",
    "normalized_value",
    "normalized_unit",
    "validation_status",
    "quality_flags",
    "group_value",
    "metric_value",
    "record_count",
}


def validate_generated_sql(
    *,
    sql_bundle: GeneratedSql,
    plan: QueryPlan | None = None,
) -> SqlValidationResult:
    normalized_sql = _normalize_sql(sql_bundle.sql)
    issues: list[SqlValidationIssue] = []

    if not normalized_sql.lower().startswith("select "):
        issues.append(_issue("not_select", "Only SELECT statements are allowed."))

    for code, pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, normalized_sql, flags=re.IGNORECASE):
            issues.append(_issue(code, f"Forbidden SQL pattern detected: {code}."))

    if f"from {SAFE_RELATION_NAME}".lower() not in normalized_sql.lower():
        issues.append(_issue("relation_not_whitelisted", "SQL must read only from the safe relation whitelist."))

    if normalized_sql.lower().count(" from ") != 1:
        issues.append(_issue("multiple_relations", "Only a single safe relation may appear in the SQL statement."))

    limit_match = re.search(r"\blimit\s+%s\b", normalized_sql, flags=re.IGNORECASE)
    if limit_match is None:
        issues.append(_issue("missing_limit", "All SQL statements must include a parameterized LIMIT clause."))

    enforced_limit = _extract_limit(sql_bundle.parameters)
    if enforced_limit is None:
        issues.append(_issue("missing_limit_parameter", "LIMIT parameter is missing or not numeric."))
    elif enforced_limit > MAX_RECORD_LIMIT:
        issues.append(_issue("limit_too_high", f"LIMIT {enforced_limit} exceeds the configured cap."))

    if plan is not None:
        issues.extend(_validate_plan_alignment(normalized_sql=normalized_sql, plan=plan))

    issues.extend(_validate_identifiers(normalized_sql))

    relation_names = [SAFE_RELATION_NAME] if SAFE_RELATION_NAME in sql_bundle.relation_names else list(sql_bundle.relation_names)
    return SqlValidationResult(
        valid=not issues,
        normalized_sql=normalized_sql,
        enforced_limit=enforced_limit,
        relation_names=relation_names,
        issues=issues,
    )


def _validate_plan_alignment(*, normalized_sql: str, plan: QueryPlan) -> list[SqlValidationIssue]:
    issues: list[SqlValidationIssue] = []
    lowered = normalized_sql.lower()

    if plan.intent == "select_records" and " group by " in lowered:
        issues.append(_issue("unexpected_group_by", "Record listing SQL must not contain GROUP BY."))

    if plan.intent == "aggregate":
        if "metric_value" not in lowered:
            issues.append(_issue("missing_metric_projection", "Aggregation SQL must project metric_value."))
        if plan.grouping and f"group by {plan.grouping[0]}".lower() not in lowered:
            issues.append(_issue("missing_grouping", "SQL is missing the required grouping clause."))
        if not plan.grouping and " group by " in lowered:
            issues.append(_issue("unexpected_grouping", "SQL groups rows even though the plan does not."))

    if plan.target_measure is not None and "variable = %s" not in normalized_sql:
        issues.append(_issue("missing_measure_filter", "Measure-aware plans must constrain the canonical variable."))

    return issues


def _validate_identifiers(normalized_sql: str) -> list[SqlValidationIssue]:
    sql_without_literals = re.sub(r"'[^']*'", "''", normalized_sql.lower())
    tokens = re.findall(r"\b[a-z_][a-z0-9_]*\b", sql_without_literals)
    issues: list[SqlValidationIssue] = []
    for token in tokens:
        if token == "s":
            continue
        if token in SQL_KEYWORDS or token in ALLOWED_IDENTIFIERS:
            continue
        if token in SAFE_FILTER_FIELDS or token in SAFE_GROUP_FIELDS:
            continue
        if token == "safe":
            continue
        issues.append(_issue("identifier_not_allowed", f"Identifier '{token}' is not part of the safe SQL subset."))
        break
    return issues


def _extract_limit(parameters: list[object]) -> int | None:
    if not parameters:
        return None
    limit_value = parameters[-1]
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        return None
    return limit_value


def _issue(code: str, message: str) -> SqlValidationIssue:
    return SqlValidationIssue(code=code, message=message, severity="error")


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())
