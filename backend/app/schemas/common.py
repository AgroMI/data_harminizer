from __future__ import annotations

from typing import Literal

ColumnType = Literal["text", "numeric", "date"]
UploadStatus = Literal["preview_ready", "committed", "failed"]
AggregationGroupBy = Literal["variety", "treatment", "location", "validation_status"]
AggregationMetric = Literal["avg_normalized_value", "count"]
NLQueryIntentType = Literal["list_records", "aggregate", "top_group", "unsupported"]
NLQueryResultType = Literal["records", "aggregation", "top_group", "unsupported"]
RetrievalSourceType = Literal[
    "raw_artifact",
    "sheet_manifest",
    "parse_warning",
    "preview_block",
    "schema_doc",
    "canonical_catalog",
    "unit_doc",
    "validation_doc",
    "query_metadata",
]
ToolCategory = Literal["query", "metadata", "conversion", "retrieval"]
