# Tests

This repository now contains four backend validation layers:

- unit / fake DB tests
  - fast feedback for ETL heuristics, semantic mapping, harmonized reads and legacy tool wrappers
- tabular reader tests
  - CSV, semicolon-delimited CSV, TSV and text encoding handling before preview generation
- MCP + text-to-SQL tests
  - planner, SQL validator, MCP tool chain, audit log behavior and the high-level pipeline endpoint
- reproducible benchmark tests
  - dataset sanity checks and the in-memory text-to-SQL benchmark runner
- real PostgreSQL e2e tests
  - real Excel upload/preview/edit/commit/query/retrieval/answer/text-to-SQL round-trips

## Main backend test files

Core unit / fake DB coverage:

- `tests/backend/test_etl_type_inference.py`
- `tests/backend/test_tabular_reader.py`
- `tests/backend/test_block_detector_horizontal_split.py`
- `tests/backend/test_semantic_mapping_flow.py`
- `tests/backend/test_unit_harmonization.py`
- `tests/backend/test_quality_validation.py`
- `tests/backend/test_harmonized_query_api.py`
- `tests/backend/test_nl_query_api.py`
- `tests/backend/test_retrieval_api.py`
- `tests/backend/test_tool_api.py`
- `tests/backend/test_answer_api.py`

MCP + text-to-SQL coverage:

- `tests/backend/test_text_to_sql_sql_validator.py`
- `tests/backend/test_mcp_api.py`
- `tests/backend/test_text_to_sql_pipeline.py`

Benchmark coverage:

- `tests/backend/test_text_to_sql_benchmark_dataset.py`
- `tests/backend/test_text_to_sql_benchmark_runner.py`
- existing legacy NL-query benchmark tests under `tests/backend/test_nl_query_benchmark_*.py`

Real PostgreSQL e2e coverage:

- `tests/backend/test_e2e_real_postgres_upload_preview.py`
- `tests/backend/test_e2e_real_postgres_harmonized_query.py`
- `tests/backend/test_e2e_real_postgres_nl_query.py`
- `tests/backend/test_e2e_real_postgres_answer.py`
- `tests/backend/test_e2e_real_postgres_retrieval_tools.py`
- `tests/backend/test_e2e_real_postgres_text_to_sql.py`

## Excel fixtures

See `tests/fixtures/README.md`.

The e2e suite uses:

- `simple_semantic_fixture.xlsx`
  - single-sheet harmonization path with `yield t/ha`, `moisture %`, `plant_height m`
  - includes an outlier-like `yield` row for validation
- `multi_sheet_fixture.xlsx`
  - two-sheet workbook with two detected blocks
  - demonstrates canonical dimensions and measures across multiple sheets
- `noisy_fixture.xlsx`
  - sparse title row, two-row header, missing values, duplicate candidates and one auxiliary sheet without detected blocks
  - demonstrates canonical convergence from `yield_kg_ha` into `yield`

## Run the fast backend suite

```bash
docker compose run --rm -v "$PWD":/app backend pytest \
  /app/tests/backend/test_etl_type_inference.py \
  /app/tests/backend/test_block_detector_horizontal_split.py \
  /app/tests/backend/test_semantic_mapping_flow.py \
  /app/tests/backend/test_unit_harmonization.py \
  /app/tests/backend/test_quality_validation.py \
  /app/tests/backend/test_harmonized_query_api.py \
  /app/tests/backend/test_nl_query_api.py \
  /app/tests/backend/test_retrieval_api.py \
  /app/tests/backend/test_tool_api.py \
  /app/tests/backend/test_answer_api.py \
  /app/tests/backend/test_text_to_sql_sql_validator.py \
  /app/tests/backend/test_mcp_api.py \
  /app/tests/backend/test_text_to_sql_pipeline.py \
  /app/tests/backend/test_text_to_sql_benchmark_dataset.py \
  /app/tests/backend/test_text_to_sql_benchmark_runner.py -q
```

## Run the text-to-SQL benchmark CLI

```bash
docker compose run --rm -v "$PWD":/app backend python /app/backend/scripts/run_text_to_sql_benchmark.py
```

## Run real PostgreSQL e2e validation

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

## Successful result

The full backend validation is considered successful if:

- upload -> preview -> save -> commit works on real Excel files
- canonical harmonization and unit normalization are stable
- quality validation still marks `warning` and `invalid` rows deterministically
- harmonized query endpoints stay read-only and return expected canonical fields
- the legacy NL-query MVP still works for its supported templates
- the internal MCP tool list is discoverable and typed
- the text-to-SQL chain produces query plans, SQL, validation output and executed results
- unsafe SQL and raw-dump style prompts are rejected
- MCP tool calls are audit logged with correlation IDs
- the reproducible benchmark remains green on the golden dataset
