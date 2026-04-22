from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypeAlias

NLIntentType: TypeAlias = Literal["list_records", "aggregate", "top_group", "unsupported"]
NLResultType: TypeAlias = Literal["records", "aggregation", "top_group", "unsupported"]
ErrorCategory: TypeAlias = Literal[
    "unsupported_misclassification",
    "wrong_intent_type",
    "wrong_group_by",
    "wrong_metric",
    "wrong_filter",
    "wrong_top_group",
    "wrong_result_shape",
    "wrong_result_content",
]


@dataclass(frozen=True, slots=True)
class QueryPlanExpectation:
    variable: str | None = None
    group_by: str | None = None
    metric: str | None = None
    include_invalid: bool | None = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregationExpectation:
    group_value: str | None
    metric_value: float | int
    record_count: int | None = None
    normalized_unit: str | None = None


@dataclass(frozen=True, slots=True)
class TopGroupExpectation:
    group_value: str | None
    metric_value: float | int
    record_count: int | None = None
    normalized_unit: str | None = None


@dataclass(frozen=True, slots=True)
class ResultExpectation:
    record_keys: tuple[str, ...] = ()
    aggregation_items: tuple[AggregationExpectation, ...] = ()
    top_group: TopGroupExpectation | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkQuestion:
    id: str
    question: str
    expected_supported: bool
    expected_intent_type: NLIntentType
    expected_result_type: NLResultType
    expected_query_plan: QueryPlanExpectation = field(default_factory=QueryPlanExpectation)
    expected_result: ResultExpectation = field(default_factory=ResultExpectation)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FieldComparison:
    field_name: str
    expected: Any
    actual: Any
    matched: bool


@dataclass(frozen=True, slots=True)
class BenchmarkQuestionResult:
    id: str
    question: str
    passed: bool
    supported_match: bool
    intent_match: bool
    result_type_match: bool
    plan_field_matches: dict[str, bool]
    result_shape_match: bool
    result_content_match: bool
    result_match: bool
    error_categories: tuple[ErrorCategory, ...]
    actual_supported: bool
    actual_intent_type: str | None
    actual_result_type: str | None
    actual_query_plan: dict[str, Any]
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AccuracyMetric:
    correct: int
    total: int

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.correct / self.total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "total": self.total,
            "accuracy": self.accuracy,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRunReport:
    dataset_name: str
    total_questions: int
    supported_classification_accuracy: AccuracyMetric
    intent_accuracy: AccuracyMetric
    result_type_accuracy: AccuracyMetric
    query_plan_field_accuracy: AccuracyMetric
    result_shape_accuracy: AccuracyMetric
    result_content_accuracy: AccuracyMetric
    result_accuracy: AccuracyMetric
    plan_field_breakdown: dict[str, AccuracyMetric]
    error_category_counts: dict[str, int]
    questions: list[BenchmarkQuestionResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "total_questions": self.total_questions,
            "supported_classification_accuracy": self.supported_classification_accuracy.to_dict(),
            "intent_accuracy": self.intent_accuracy.to_dict(),
            "result_type_accuracy": self.result_type_accuracy.to_dict(),
            "query_plan_field_accuracy": self.query_plan_field_accuracy.to_dict(),
            "result_shape_accuracy": self.result_shape_accuracy.to_dict(),
            "result_content_accuracy": self.result_content_accuracy.to_dict(),
            "result_accuracy": self.result_accuracy.to_dict(),
            "plan_field_breakdown": {
                field_name: metric.to_dict()
                for field_name, metric in self.plan_field_breakdown.items()
            },
            "error_category_counts": dict(self.error_category_counts),
            "questions": [item.to_dict() for item in self.questions],
        }
