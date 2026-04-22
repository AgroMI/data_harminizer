# Thesis Project Scaffold (Minimal Scope)

This repository contains a runnable scaffold for:
- Excel upload from frontend.
- Backend preview parsing (block count, missing data summary, type suggestions, date issues).
- Preview edit + semantic mapping + commit flow.
- Raw artifact preservation with provenance metadata.
- Layered warehouse writes into PostgreSQL/PostGIS: `raw`, `staging`, `harmonized`.
- Harmonized REST reads and a separate query-ready read layer.
- Read-only NL-to-query MVP on top of the harmonized query layer.
- Internal MCP-style tool-serving layer with audit log and correlation IDs.
- Controlled text-to-SQL pipeline with explicit query plans, parameterized SQL generation, static SQL validation and read-only execution.
- Read-only answer assembly MVP with linked retrieval context and source references.
- Optional local-LLM-assisted hybrid planning on top of the controlled text-to-SQL and MCP layers.

## Current scope

The project is still a thesis-oriented demonstrator, but the preview editor now supports
column-level semantic mapping with a controlled canonical catalog in addition to type overrides:

- `ignore`
- `date`
- `dimension`
- `measure`

Supported canonical dimensions:

- `plot_id`
- `variety`
- `treatment`
- `location`

Supported canonical measures:

- `yield`
- `moisture`
- `plant_height`

Supported source units and canonical target units:

- `yield`
  - source: `kg/ha`, `t/ha`
  - canonical: `kg/ha`
- `moisture`
  - source: `%`
  - canonical: `%`
- `plant_height`
  - source: `cm`, `m`
  - canonical: `cm`

The commit step uses this mapping to create harmonized observations with explicit canonical fields and lineage:

- `source_sheet`
- `source_row_index`
- `source_column`
- `observation_date`
- `plot_id`
- `variety`
- `treatment`
- `location`
- `variable`
- `value`
- `unit`
- `normalized_value`
- `normalized_unit`
- `validation_status`
- `quality_flags`
- `dimensions_json`

The `raw` layer now preserves the original uploaded workbook separately from the preview snapshot:

- `raw.artifacts` stores the original file bytes in PostgreSQL (`bytea`)
- SHA-256 hash, MIME type, file size and upload timestamp are recorded
- parser version, preview generation time and a sheet manifest are recorded
- `raw.upload_sessions` references the raw artifact and stores the derived `preview_json`

What is intentionally still out of scope:

- enterprise-grade warehouse modeling
- background jobs / async processing
- authentication / user management
- advanced ontology or dictionary-based semantic alignment
- rich spatial/PostGIS usage
- MIAPPE-complete domain coverage
- external MCP transport / stdio protocol compatibility
- LLM-based SQL generation or vector retrieval

## Query execution modes

The text-to-SQL surface now supports three runtime modes:

- `deterministic`
  - default mode
  - current planner -> SQL generator -> SQL validator -> safe execution
- `local_llm_hybrid`
  - deterministic planner runs first
  - local model is only consulted when the deterministic plan is unsupported, ambiguous or clarification-like
  - the model can only return a structured query-plan proposal
  - the proposal is validated before it reaches SQL generation
- `local_llm_tool_orchestrated`
  - same as hybrid mode
  - before final local planning, the local model may suggest a small number of read-only MCP helper tools
  - helper tools are limited to schema/provenance context gathering and remain audited

The local model never receives direct database access and never executes SQL directly.

## Local LLM configuration

The optional local adapter expects an OpenAI-compatible chat-completions HTTP endpoint.

Relevant environment variables:

- `LOCAL_LLM_ENABLED`
- `LOCAL_LLM_HYBRID_ENABLED`
- `LOCAL_LLM_TOOL_ORCHESTRATION_ENABLED`
- `LOCAL_LLM_ENDPOINT`
- `LOCAL_LLM_MODEL`
- `LOCAL_LLM_API_KEY`
- `LOCAL_LLM_TIMEOUT_MS`
- `LOCAL_LLM_MAX_OUTPUT_TOKENS`
- `LOCAL_LLM_TEMPERATURE`

Recommended starting point for hosted OpenAI-compatible endpoints:

- `LOCAL_LLM_TIMEOUT_MS=12000`

The planner prompt is intentionally structured and may include schema context, so `4000ms` can be too aggressive for hosted APIs.

Safe defaults:

- hybrid mode is off unless explicitly enabled
- deterministic mode remains the fallback and default path
- if the local model is unavailable, invalid or disabled, the system falls back to deterministic behavior

## Safety guarantees

The optional local mode does not bypass the controlled query stack.

The following guarantees remain mandatory:

- only the safe read relation is allowed for generated SQL
- SQL must remain `SELECT`-only
- SQL validation is always mandatory
- parameterized `LIMIT` is always mandatory
- read-only execution is preserved
- timeout and row cap are preserved
- every MCP tool call remains audited
- local model calls are audited separately
- the local model never receives raw database access
- the local model never returns directly executable SQL

## Local LLM audit

When hybrid planning is enabled, model calls are written into `ops.llm_planner_audit_log`.

The audit captures:

- correlation ID
- requested mode
- provider/model name
- prompt template name
- success / failure
- whether the structured output validated
- whether fallback was used
- serialized request / response payloads

The API surface also exposes:

- `GET /api/llm/audit`

## Benchmark notes

The text-to-SQL benchmark dataset already contains categories such as:

- aggregation
- alias
- clarification
- count
- records
- temporal
- top_n
- unsafe

These categories are useful for comparing deterministic and local-hybrid behavior without relaxing safety rules.

## Top-level structure

- `backend`
- `frontend`
- `db/migrations`
- `etl`
- `infra`
- `tests`

## Prerequisites

- Docker
- Docker Compose

## Run

```bash
docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Backend docs: http://localhost:8000/docs
- PostgreSQL/PostGIS: `localhost:5432`

## Database initialization path

On backend startup, migrations are applied automatically in order from:

- `./db/migrations/*.sql`

using `backend/scripts/run_migrations.py` invoked by `backend/start.sh`.

## Minimal flow

1. Open http://localhost:3000/upload
2. Upload `.xlsx` or `.xls` file
3. Continue through the generated `/uploads/{id}` workflow
4. Review blocks, correct mapping and resolve blocking validation issues
5. Commit harmonized data
6. Browse committed rows in `http://localhost:3000/workspace`
7. Run AI-assisted questions in `http://localhost:3000/ai`

## Semantic mapping in the preview

On the preview page each detected column shows:

- original column name
- inferred type
- optional type override
- semantic role
- canonical measure selector or canonical dimension selector
- controlled source-unit selector for measure columns
- target/canonical unit hint for measure columns
- warnings for ambiguous typing, date parsing and missingness

The editor persists the mapping in `preview_json`, so saved state is loaded back reliably.
The UI now uses controlled selectors instead of free-text canonical naming.

## Raw artifact and provenance model

The current source-of-truth layers are intentionally simple, but now explicitly separated:

- `raw.artifacts`
  - original uploaded workbook bytes
  - `original_filename`
  - `mime_type`
  - `file_size_bytes`
  - `file_hash_sha256`
  - `uploaded_at`
  - `parser_version`
  - `storage_type`
  - `sheet_manifest`
  - `preview_generated_at`
  - `parse_warning_summary`
- `raw.upload_sessions`
  - upload/session status
  - reference to the raw artifact
  - derived `preview_json`
- `staging.observations`
  - observation rows derived from the preview snapshot
  - includes explicit canonical dimension columns (`plot_id`, `variety`, `treatment`, `location`)
  - keeps source `value` / `unit` and computed `normalized_value` / `normalized_unit`
  - adds `validation_status` and `quality_flags`
- `harmonized.observations`
  - committed canonical observation rows with explicit domain fields, normalized units, lineage and quality metadata

The current simplification is deliberate:

- the commit step still reads from `preview_json`
- the raw artifact is preserved for provenance and replayability, but the pipeline is not yet reparsed from raw on commit
- storage is local to PostgreSQL, not an external object store
- the canonical catalog is intentionally small and thesis-scoped
- old rows are backfilled in migration by copying `value/unit` into `normalized_value/normalized_unit`; recommit is the authoritative way to recalculate conversions

## Validation

The repository now contains two validation layers:

- unit / fake DB tests for ETL and semantic mapping logic
- real PostgreSQL end-to-end validation with real `.xlsx` fixture files

The real e2e validation covers:

- `POST /uploads`
- `GET /uploads/{id}`
- `GET /uploads/{id}/preview`
- `POST /uploads/{id}/edits`
- `POST /uploads/{id}/commit`
- `GET /api/harmonized/observations?upload_session_id=...`

The commit pipeline now also applies a deterministic data-quality checkpoint to harmonized rows.

Validation statuses:

- `valid`
- `warning`
- `invalid`

Supported quality flags:

- `missing_required_dimension`
- `missing_observation_date`
- `missing_unit`
- `missing_measure_value`
- `duplicate_candidate`
- `outlier_candidate`

Current policy:

- warning rows are committed and remain queryable
- invalid rows are also committed, but explicitly marked instead of being silently dropped
- duplicate detection is deterministic and scoped to the canonical observation key
- outlier detection is currently rule-based on normalized values for `yield`, `moisture` and `plant_height`

Fixtures used by the e2e suite:

- `tests/fixtures/simple_semantic_fixture.xlsx`
  - single-sheet harmonization path with `yield t/ha`, `moisture %` and `plant_height m`
  - includes a high `yield` value to demonstrate `outlier_candidate`
- `tests/fixtures/multi_sheet_fixture.xlsx`
  - two-sheet workbook with separate `yield` and `moisture` blocks
- `tests/fixtures/noisy_fixture.xlsx`
  - sparse title row, two-row header, missing values, duplicate candidates and parse warnings
  - demonstrates `yield_kg_ha -> yield @ kg/ha`

Run the full real e2e validation with:

```bash
docker compose up -d db
docker compose run --rm backend python backend/scripts/run_migrations.py
docker compose run --rm -v "$PWD":/app backend python /app/tests/fixtures/generate_excel_fixtures.py
docker compose run --rm -v "$PWD":/app backend pytest \
  /app/tests/backend/test_e2e_real_postgres_upload_preview.py \
  /app/tests/backend/test_e2e_real_postgres_harmonized_query.py \
  /app/tests/backend/test_e2e_real_postgres_nl_query.py \
  /app/tests/backend/test_e2e_real_postgres_answer.py \
  /app/tests/backend/test_e2e_real_postgres_retrieval_tools.py \
  /app/tests/backend/test_e2e_real_postgres_text_to_sql.py -q
```

This complements the fake DB tests: the unit layer validates isolated heuristics quickly, while the e2e layer proves that the full upload -> preview -> save -> commit -> observations pipeline works with real Excel files and a real PostgreSQL database.

## Commit behavior

The commit step now uses semantic roles instead of only inferred types:

- `date` -> becomes `observation_date`
- `dimension` -> fills canonical columns such as `plot_id`, `variety`, `treatment`, `location`
- `measure` -> produces harmonized observation rows using controlled canonical variables
- `ignore` -> produces no records

The harmonized `variable` is now the selected canonical measure (`yield`, `moisture`, `plant_height`).
For measures, `value` / `unit` are the source values and `normalized_value` / `normalized_unit` are the canonical outputs.
After commit, each observation also carries `validation_status` and `quality_flags`.
The observations API can also be filtered by `variable`, `variety`, `location`, `treatment`, `normalized_unit`, `validation_status` and `quality_flag`.

## Query-ready read layer

The repository now also contains a separate read-only query layer on top of `harmonized.observations`.

Purpose:

- keep ingestion/commit logic separate from data access
- expose stable, canonical and validation-aware read models
- prepare a clean target surface for a later Text-to-SQL MVP

New query endpoints:

- `GET /api/harmonized/observations`
- `GET /api/harmonized/aggregations`
- `GET /api/harmonized/query-metadata`

The detailed list endpoint supports:

- `upload_session_id`
- `variable`
- `variety`
- `location`
- `treatment`
- `plot_id`
- `observation_date_from`
- `observation_date_to`
- `validation_status`
- `quality_flag`
- `normalized_unit`

The aggregation endpoint supports:

- `group_by=variety|treatment|location|validation_status`
- `metric=avg_normalized_value|count`
- optional reuse of the same canonical/date/validation filters

Aggregation policy:

- non-status aggregations exclude `invalid` rows by default
- `include_invalid=true` can override this
- warning and invalid records remain queryable through the list endpoint and validation filters

The query metadata endpoint returns:

- supported filters
- supported aggregation dimensions and metrics
- available canonical `variable` values in the data
- available `normalized_unit` values
- available canonical dimension values (`variety`, `location`, `treatment`, `plot_id`)
- available `validation_status` values
- available `quality_flag` values

## Default frontend flow

The frontend is now organized around a small workflow-first route set:

- `/`
  - concise landing page with the main workflow only
- `/upload`
  - single-purpose upload screen with a large dropzone and recent uploads
- `/uploads/{id}?stage=review|mapping|validation|commit`
  - guided step-based workflow for one upload session
- `/workspace`
  - harmonized data browsing with filters, summary cards and row detail
- `/ai`
  - one advanced screen for AI query, MCP tools, audit and benchmark

The default browser path is:

1. `http://localhost:3000/upload`
2. `http://localhost:3000/uploads/{id}?stage=review`
3. `...stage=mapping`
4. `...stage=validation`
5. `...stage=commit`
6. `http://localhost:3000/workspace`
7. `http://localhost:3000/ai`

Primary vs. advanced UI is now explicit:

- primary workflow UI
  - upload
  - staged review/mapping/validation/commit flow
  - harmonized data workspace
- advanced UI
  - MCP tool payloads
  - query plan
  - generated SQL
  - validation details
  - audit log
  - benchmark results

Technical details no longer live on separate public demo pages. They are grouped behind tabs and collapsible panels on the dedicated AI screen.

## Frontend pages

- `http://localhost:3000/upload`
  - clean upload entry point
- `http://localhost:3000/workspace`
  - harmonized data browser with filter-first layout
- `http://localhost:3000/ai`
  - advanced AI screen with four tabs:
    - question answering
    - MCP tool runner
    - audit log
    - benchmark viewer

The upload detail page itself is now the workflow surface:

- `http://localhost:3000/uploads/{id}?stage=review`
- `http://localhost:3000/uploads/{id}?stage=mapping`
- `http://localhost:3000/uploads/{id}?stage=validation`
- `http://localhost:3000/uploads/{id}?stage=commit`

## NL-to-query MVP

The repository now also contains a narrow, schema-aware natural language query layer above the harmonized read layer.

Endpoint:

- `POST /api/harmonized/nl-query`

Input:

- `question`

Response fields:

- `question`
- `supported`
- `recognized_intent`
- `query_plan`
- `result_type`
- `results`
- `explanation`

The NL layer is intentionally not a free-form SQL generator. Instead it follows this chain:

1. natural language question
2. explicit query plan
3. execution against the existing harmonized query service
4. read-only result payload

Currently supported question types:

- average `yield` by `variety`
- average `yield` by `treatment`
- average `yield` by `location`
- list warning and/or invalid records
- list records for a recognized `location`
- list records for a recognized `variety`
- list records for a recognized canonical `variable`
- highest average `yield` by `variety`
- highest average `yield` by `treatment`

The parser is rule-based and schema-aware:

- it uses the controlled canonical measure vocabulary
- it uses the harmonized query metadata for available dimension values
- it only maps to known list/aggregation/top-group intents
- unsupported questions are rejected with an explicit `supported=false` response

This keeps the MVP:

- read-only
- deterministic
- auditable
- easy to explain in a thesis context

Current limitations:

- no free-form SQL
- no joins outside the harmonized read model
- no charting or conversational memory
- only a small set of list and aggregation templates is recognized

## NL-query benchmark protocol

The repository now also contains a separate benchmark and evaluation layer for the existing
read-only NL-query MVP.

Purpose:

- keep runtime query logic separate from benchmark fixtures and scoring
- evaluate the current NL layer with a controlled, reproducible golden dataset
- measure both query-plan correctness and returned result correctness
- produce auditable outputs for thesis benchmarking and regression checks

Location:

- evaluation code: `backend/app/evaluation/`
- golden benchmark questions: `backend/app/evaluation/data/nl_query_benchmark_dataset.json`
- controlled seed rows: `backend/app/evaluation/data/nl_query_benchmark_seed_rows.json`
- CLI runner: `backend/scripts/run_nl_query_benchmark.py`

The golden dataset is intentionally hand-authored JSON, not generated dynamically.
Each benchmark question stores:

- `id`
- `question`
- `expected_supported`
- `expected_intent_type`
- `expected_query_plan`
- `expected_result_type`
- `expected_result`
- optional `notes`

Covered question classes:

- `aggregate`
- `list_records`
- `top_group`
- `unsupported`

The default benchmark covers:

- average yield by `variety`
- average yield by `treatment`
- average yield by `location`
- warning and invalid record listing
- location-based filtering
- variety-based filtering
- variable-based filtering
- highest average yield questions
- unsupported / out-of-scope prompts

Metrics:

- supported classification accuracy
- intent accuracy
- result type accuracy
- query-plan field accuracy
- query-plan field breakdown
- result shape accuracy
- result content accuracy
- overall result accuracy
- error-category counts

Evaluated query-plan fields:

- `supported`
- `intent_type`
- `variable`
- `group_by`
- `metric`
- relevant `filters`
- `include_invalid`
- `result_type`

Error categories:

- `unsupported_misclassification`
- `wrong_intent_type`
- `wrong_group_by`
- `wrong_metric`
- `wrong_filter`
- `wrong_top_group`
- `wrong_result_shape`
- `wrong_result_content`

Run the benchmark with:

```bash
docker compose run --rm -v "$PWD":/app backend python /app/backend/scripts/run_nl_query_benchmark.py
```

Optional output files:

```bash
docker compose run --rm -v "$PWD":/app backend \
  python /app/backend/scripts/run_nl_query_benchmark.py \
  --json-output /app/tmp/nl_query_benchmark_report.json \
  --markdown-output /app/tmp/nl_query_benchmark_summary.md
```

The runner executes the real `backend.app.services.nl_query_service.execute_nl_query`
function against a controlled in-memory read backend. This keeps the benchmark deterministic
while still measuring the actual runtime NL interpretation and execution path.

Current limitations of the benchmark:

- it evaluates the existing deterministic NL-query MVP, not a free-form Text-to-SQL system
- it uses a controlled golden fixture dataset, not arbitrary live production data
- result correctness is measured against the controlled seed rows and expected outputs
- unsupported coverage is intentionally explicit and bounded, not open-domain

This protocol is meant to support the thesis benchmarking section as an auditable evaluation
of the current schema-aware NL-query MVP, without overstating it as a general Text-to-SQL engine.

## Internal MCP server and controlled text-to-SQL

The repository now also contains a separate internal MCP-style server layer and a controlled
text-to-SQL pipeline above the harmonized safe read surface.

Primary runtime endpoints:

- `GET /api/mcp/tools`
- `POST /api/mcp/invoke`
- `GET /api/mcp/audit`
- `POST /api/text-to-sql/query`

Primary implementation modules:

- `backend/app/mcp/server.py`
  - tool discovery, invocation flow, correlation ID handling and unified envelopes
- `backend/app/mcp/tool_registry.py`
  - explicit MCP tool registry
- `backend/app/mcp/tool_types.py`
  - input/output schema-backed tool contracts
- `backend/app/mcp/audit.py`
  - audit log write/read helpers
- `backend/app/mcp/tools/core_tools.py`
  - the MCP tool implementations
- `backend/app/text_to_sql/models.py`
  - explicit query plan and SQL validation models
- `backend/app/text_to_sql/planner.py`
  - rule-based NL understanding into an explicit query plan
- `backend/app/text_to_sql/sql_generator.py`
  - SQL generation strictly from query plans
- `backend/app/text_to_sql/sql_validator.py`
  - static safe-SQL validation
- `backend/app/text_to_sql/sql_executor.py`
  - read-only, timeout-limited SQL execution
- `backend/app/text_to_sql/service.py`
  - end-to-end pipeline orchestration through the MCP tool chain
- `db/migrations/011_add_safe_query_layer_and_mcp_audit.sql`
  - `safe.harmonized_observations_v1` and `ops.mcp_tool_audit_log`

Implemented MCP tools:

- `describe_schema`
- `plan_query`
- `generate_sql`
- `validate_sql`
- `execute_sql`
- `explain_metadata`
- `retrieve_evidence`

The intended AI access pattern is now explicit:

1. a natural-language question is submitted
2. `plan_query` produces a JSON-serializable query plan
3. `generate_sql` renders parameterized SQL only from that plan
4. `validate_sql` checks the SQL against the safe subset
5. `execute_sql` runs only validated SQL in a read-only context
6. every tool call is audit logged with a correlation ID

Current query-plan fields:

- `status`
- `intent`
- `source_relation`
- `selected_measures`
- `selected_dimensions`
- `filters`
- `aggregations`
- `grouping`
- `ordering`
- `limit`
- `unit_handling`
- `ambiguity_flags`
- `validation_notes`
- `trace`
- `target_measure`
- `result_type`

Current SQL safety guarantees:

- only `SELECT` is accepted
- only `safe.harmonized_observations_v1` is whitelisted
- DDL/DML keywords are rejected
- `pg_catalog` and `information_schema` are rejected
- `JOIN` is rejected
- `LIMIT` is mandatory
- `LIMIT` is capped
- execution uses `BEGIN READ ONLY`
- execution uses `statement_timeout`
- every tool call is written into `ops.mcp_tool_audit_log`

The high-level `/api/text-to-sql/query` endpoint is intentionally built on the MCP server,
not by bypassing it. This keeps the thesis claim defensible: the AI-facing access path goes
through explicit internal tools instead of direct database access.

Supported text-to-SQL classes in the current implementation:

- bounded record listing on the safe view
- average aggregations over canonical normalized measures
- count aggregations
- grouping by canonical dimensions and `validation_status`
- temporal filtering by exact date or year
- top-N and lowest-N aggregate requests
- ambiguity handling for missing measure / missing grouping / multiple measures
- safe rejection of raw dump and SQL-like requests

Current limitations:

- the planner is still deterministic and rule-based
- only one safe relation is currently exposed
- no join planning exists
- no external MCP transport exists yet
- no LLM is used to generate query plans

## Text-to-SQL benchmark protocol

The repository now also contains a dedicated benchmark for the controlled text-to-SQL chain.

Location:

- dataset: `backend/app/evaluation/data/text_to_sql_benchmark_dataset.json`
- seed rows: `backend/app/evaluation/data/nl_query_benchmark_seed_rows.json`
- runner: `backend/app/evaluation/text_to_sql_benchmark_runner.py`
- CLI: `backend/scripts/run_text_to_sql_benchmark.py`

The benchmark currently covers 50 hand-authored questions across:

- aggregation
- filtered record listing
- temporal filters
- top-N / ordering
- domain alias handling
- unsupported queries
- adversarial / unsafe prompts
- clarification-required prompts

Reported metrics:

- query plan correctness
- SQL validity rate
- execution success rate
- answer correctness
- unsupported query rate
- rejected unsafe query rate

Run the benchmark with:

```bash
docker compose run --rm -v "$PWD":/app backend python /app/backend/scripts/run_text_to_sql_benchmark.py
```

Optional output files:

```bash
docker compose run --rm -v "$PWD":/app backend \
  python /app/backend/scripts/run_text_to_sql_benchmark.py \
  --json-output /app/tmp/text_to_sql_benchmark_report.json \
  --markdown-output /app/tmp/text_to_sql_benchmark_summary.md
```

## Retrieval / RAG-lite protocol MVP

The repository now also contains a narrow, read-only retrieval layer that sits next to the
harmonized query layer and returns structured context documents.

Purpose:

- attach provenance and schema context to query results
- support direct search over controlled system context sources
- keep retrieval separate from runtime query execution
- prepare a later RAG or MCP direction without introducing an LLM dependency

Design constraints:

- no vector database
- no embeddings
- no generative answer engine
- no write operations
- deterministic, auditable retrieval only

Architecture:

- `backend/app/services/retrieval_service.py`
  - orchestration only
- `backend/app/retrieval/retrieval_sources.py`
  - controlled document building from existing raw/provenance and schema sources
- `backend/app/retrieval/retrieval_search.py`
  - deterministic token-overlap search and snippet building
- `backend/app/retrieval/retrieval_assembly.py`
  - context summary, source summary and explanation bundle assembly
- `backend/app/retrieval/retrieval_types.py`
  - explicit retrieval document and match models

Indexed source categories:

- `raw_artifact`
- `sheet_manifest`
- `parse_warning`
- `preview_block`
- `schema_doc`
- `canonical_catalog`
- `unit_doc`
- `validation_doc`
- `query_metadata`

The retrieval document model is explicit and structured:

- `document_id`
- `source_type`
- `title`
- `text`
- `metadata`
- optional `upload_session_id`

Endpoints:

- `GET /api/retrieval/context`
- `POST /api/retrieval/search`

`GET /api/retrieval/context` is the query-related context endpoint.
It accepts:

- optional `upload_session_id`
- optional canonical `variable`
- optional `question`
- `include_schema_context`
- `include_raw_context`
- `limit`

It returns:

- `summary`
- `context_documents`
- `sources`
- `explanation_sections`
- optional `query_metadata_snapshot`

`POST /api/retrieval/search` is the direct context search endpoint.
It accepts:

- `query`
- optional `upload_session_id`
- `limit`

It returns a ranked list of structured retrieval hits with:

- source type
- title
- snippet
- metadata
- optional upload/session binding
- deterministic score

Context sources currently covered:

- raw artifact metadata from `raw.artifacts`
- upload/session-linked preview snapshot from `raw.upload_sessions`
- sheet manifest and parse warnings
- preview block descriptions
- canonical measure and dimension catalog docs
- unit model docs
- validation and quality-flag docs
- live harmonized query metadata snapshot

The harmonized query workbench now also includes a small retrieval demo area with:

- direct context search
- query-related "show related context"
- raw/provenance demo action
- schema/validation demo action

Current limitations:

- retrieval is rule-based and deterministic, not semantic-vector search
- document sources are intentionally controlled and small
- no free-form answer generation is performed
- no conversational memory exists
- no external MCP or LLM connector is required yet

This keeps the current implementation honest: it is a retrieval protocol MVP that demonstrates
how harmonized query results can be paired with provenance and schema context, while remaining
strictly read-only and easy to audit in a thesis context.

## RAG answer assembly MVP

The repository now also contains a narrow answer assembly layer above the existing
NL-query and retrieval services.

Purpose:

- combine a harmonized query result and linked retrieval context into one response bundle
- return a short, deterministic answer summary without free-form generation
- keep the answer read-only and auditable with explicit source references
- expose section-level and finding-level source linkage
- surface validation and provenance context directly inside the answer bundle
- demonstrate a thesis-safe bridge from retrieval to a later RAG-style answer layer

Architecture:

- `backend/app/services/answer_assembly_service.py`
  - orchestration only
- `backend/app/services/nl_query_service.py`
  - existing read-only question interpretation and query execution
- `backend/app/services/retrieval_service.py`
  - existing schema/provenance context retrieval
- `backend/app/schemas/answer.py`
  - explicit request and response contracts for answer bundles

Endpoint:

- `POST /api/rag/answer`

It accepts:

- optional `question`
- optional `upload_session_id`
- optional canonical `variable`
- `include_context`
- `include_schema_context`
- `include_raw_context`

The request must include at least one of:

- `question`
- `upload_session_id`
- `variable`

It returns:

- `question`
- `supported`
- `recognized_intent`
- `query_plan`
- `result_type`
- `results`
- `answer_summary`
- `answer_sections`
- `key_findings`
- `quality_notes`
- `context_documents`
- `sources`
- optional `query_metadata_snapshot`

Answer assembly rules:

- no free-form LLM text generation is used
- the answer summary is built from the actual query result and linked retrieval context only
- query execution stays in the harmonized query layer
- context retrieval stays in the retrieval layer
- sources are explicit document references, not hidden citations
- each answer section includes `source_ids`
- each key finding includes `evidence_source_ids`
- source items include stable `source_id` values and can represent either query-result evidence or retrieval documents

Current answer bundle structure:

- `answer_summary`
  - short deterministic overview
- `answer_sections`
  - structured narrative blocks such as result overview, quality context, source context and limitations
- `key_findings`
  - short factual statements derived from the query result
- `quality_notes`
  - validation-aware notes derived from returned statuses, quality flags or aggregation scope
- `sources`
  - explicit evidence entries with `source_id`, `source_type`, `title`, `snippet`, metadata and optional upload binding

Supported answer modes:

- natural-language question to answer bundle
- direct scope answer from explicit `upload_session_id` and/or canonical `variable`

The harmonized workbench now also includes a small answer demo area with:

- question input
- demo prompts
- "Generate answer with context"
- "Build answer from current scope"
- answer summary
- key findings
- quality notes
- source-linked answer sections
- explicit source list
- linked context documents

Why this second-level MVP is more auditable:

- answer claims point back to stable source identifiers
- the query result itself appears as a first-class evidence source
- validation and provenance are not hidden in background metadata
- the output is easier to compare across runs because the structure is deterministic

Current limitations:

- this is not a chatbot and not a multi-turn assistant
- no open-ended generation is performed
- unsupported NL questions remain unsupported; the answer layer does not expand NL-query capability
- source linking points to the controlled query-result and retrieval document set only
- the answer bundle is deterministic and thesis-scoped, not a general RAG platform

## Legacy tool abstraction compatibility layer

The repository still also contains the earlier lightweight internal tool abstraction layer above
the existing read-only services. It remains available for compatibility and demo purposes, but it
is no longer the primary AI-facing integration surface. The primary surface is now the dedicated
internal MCP-style server and the controlled text-to-SQL pipeline described above.

Purpose:

- expose existing capabilities through a consistent tool contract
- keep tool discovery and tool execution explicit and typed
- wrap the current services instead of duplicating them
- keep the available tool surface read-only and safe

Architecture:

- `backend/app/tools/tool_types.py`
  - explicit tool definition and field summary models
- `backend/app/tools/tool_registry.py`
  - explicit registry of available tools
- `backend/app/tools/tool_runner.py`
  - validation, dispatch and unified response envelope
- `backend/app/tools/query_tool.py`
  - wraps harmonized observations, aggregation and query metadata reads
- `backend/app/tools/metadata_tool.py`
  - wraps canonical catalog, unit model, validation metadata and optional live query metadata
- `backend/app/tools/unit_conversion_tool.py`
  - wraps deterministic unit normalization
- `backend/app/tools/retrieval_tool.py`
  - wraps direct retrieval search and query-related context retrieval

Available tools:

- `query_tool`
- `metadata_tool`
- `unit_conversion_tool`
- `retrieval_tool`

Unified request envelope:

- `tool_name`
- `arguments`

Unified response envelope:

- `tool_name`
- `success`
- `result`
- `error`
- `metadata`

Tool discovery endpoint:

- `GET /api/tools`

It returns:

- available tool list
- description
- category
- read-only flag
- input field summaries

Tool execution endpoint:

- `POST /api/tools/execute`

Current safety guarantees:

- all exposed tools are read-only
- no upload, edit or commit tool exists
- no arbitrary SQL execution is exposed
- no agent orchestration is implemented
- the tools only wrap existing service logic

The harmonized workbench also now includes a minimal tool demo panel with:

- available tools overview
- JSON argument editor
- unified tool response viewer
- quick demos for metadata, unit conversion, retrieval and query aggregate execution

This prepares a later MCP direction in a controlled way:

- discovery is explicit
- tool contracts are typed
- execution is already uniform
- service logic stays separate from tool adapters

Current limitations:

- no external MCP protocol server exists yet
- no remote tool transport exists
- no write tools are exposed
- the tool surface is intentionally small and thesis-scoped
