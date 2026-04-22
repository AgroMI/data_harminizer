from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ExpectedStatus = Literal["supported", "unsupported", "clarification_required"]


@dataclass(frozen=True, slots=True)
class AggregationExpectation:
    group_value: str | None
    metric_value: float | int
    record_count: int | None = None
    normalized_unit: str | None = None


@dataclass(frozen=True, slots=True)
class ResultExpectation:
    record_keys: tuple[str, ...] = ()
    aggregation_items: tuple[AggregationExpectation, ...] = ()
    count: int | None = None


@dataclass(frozen=True, slots=True)
class TextToSqlBenchmarkQuestion:
    id: str
    category: str
    question: str
    expected_status: ExpectedStatus
    expected_intent: str
    expected_result_type: str
    expected_query_plan: dict[str, Any] = field(default_factory=dict)
    expected_result: ResultExpectation = field(default_factory=ResultExpectation)
    expected_sql_valid: bool = False
    unsafe: bool = False
    notes: str | None = None


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
        return {"correct": self.correct, "total": self.total, "accuracy": self.accuracy}


@dataclass(frozen=True, slots=True)
class TextToSqlBenchmarkQuestionResult:
    id: str
    category: str
    question: str
    passed: bool
    query_plan_match: bool
    sql_valid_match: bool
    execution_success: bool
    answer_match: bool
    unsupported_match: bool
    unsafe_rejection_match: bool
    actual_status: str
    actual_intent: str
    actual_result_type: str
    actual_sql_valid: bool
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TextToSqlBenchmarkReport:
    dataset_name: str
    total_questions: int
    query_plan_correctness: AccuracyMetric
    sql_validity_rate: AccuracyMetric
    execution_success_rate: AccuracyMetric
    answer_correctness: AccuracyMetric
    unsupported_query_rate: AccuracyMetric
    rejected_unsafe_query_rate: AccuracyMetric
    questions: list[TextToSqlBenchmarkQuestionResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "total_questions": self.total_questions,
            "query_plan_correctness": self.query_plan_correctness.to_dict(),
            "sql_validity_rate": self.sql_validity_rate.to_dict(),
            "execution_success_rate": self.execution_success_rate.to_dict(),
            "answer_correctness": self.answer_correctness.to_dict(),
            "unsupported_query_rate": self.unsupported_query_rate.to_dict(),
            "rejected_unsafe_query_rate": self.rejected_unsafe_query_rate.to_dict(),
            "questions": [item.to_dict() for item in self.questions],
        }
