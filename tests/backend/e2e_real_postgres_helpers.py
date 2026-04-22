from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
MIGRATIONS_SCRIPT = ROOT / "backend" / "scripts" / "run_migrations.py"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://thesis:thesis@localhost:5432/thesis")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _db_conn() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def upload_file(client: TestClient, fixture_name: str) -> dict[str, Any]:
    file_bytes = _fixture_bytes(fixture_name)
    response = client.post(
        "/uploads",
        files={"file": (fixture_name, file_bytes, EXCEL_MIME)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_artifact"]["file_size_bytes"] == len(file_bytes)
    assert payload["raw_artifact"]["file_hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    return payload


def block_by_sheet(preview: dict[str, Any], sheet_name: str) -> dict[str, Any]:
    for block in preview["blocks"]:
        if block.get("sheet") == sheet_name:
            return block
    raise AssertionError(f"Expected block for sheet {sheet_name!r}.")


def build_edit(
    *,
    block_id: str,
    column: str,
    semantic_role: str,
    type_override: str | None = None,
    canonical_measure: str | None = None,
    canonical_dimension: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "column": column,
        "type_override": type_override,
        "semantic_role": semantic_role,
        "canonical_measure": canonical_measure,
        "canonical_dimension": canonical_dimension,
        "unit": unit,
    }


def build_simple_fixture_edits(block_id: str) -> dict[str, Any]:
    return {
        "columns": [
            build_edit(block_id=block_id, column="date", semantic_role="date"),
            build_edit(block_id=block_id, column="plot_id", semantic_role="dimension", canonical_dimension="plot_id"),
            build_edit(block_id=block_id, column="variety", semantic_role="dimension", canonical_dimension="variety"),
            build_edit(
                block_id=block_id,
                column="treatment",
                semantic_role="dimension",
                canonical_dimension="treatment",
            ),
            build_edit(block_id=block_id, column="yield_t/ha", semantic_role="measure", canonical_measure="yield", unit="t/ha"),
            build_edit(block_id=block_id, column="moisture", semantic_role="measure", canonical_measure="moisture", unit="%"),
            build_edit(
                block_id=block_id,
                column="plant_height_m",
                semantic_role="measure",
                canonical_measure="plant_height",
                unit="m",
            ),
            build_edit(block_id=block_id, column="notes", semantic_role="ignore"),
        ]
    }


def build_multi_sheet_fixture_edits(yield_block_id: str, moisture_block_id: str) -> dict[str, Any]:
    return {
        "columns": [
            build_edit(block_id=yield_block_id, column="date", semantic_role="date"),
            build_edit(block_id=yield_block_id, column="plot_id", semantic_role="dimension", canonical_dimension="plot_id"),
            build_edit(block_id=yield_block_id, column="variety", semantic_role="dimension", canonical_dimension="variety"),
            build_edit(
                block_id=yield_block_id,
                column="treatment",
                semantic_role="dimension",
                canonical_dimension="treatment",
            ),
            build_edit(block_id=yield_block_id, column="yield", semantic_role="measure", canonical_measure="yield", unit="kg/ha"),
            build_edit(block_id=yield_block_id, column="notes", semantic_role="ignore"),
            build_edit(block_id=moisture_block_id, column="date", semantic_role="date"),
            build_edit(
                block_id=moisture_block_id,
                column="plot_id",
                semantic_role="dimension",
                canonical_dimension="plot_id",
            ),
            build_edit(
                block_id=moisture_block_id,
                column="location",
                semantic_role="dimension",
                canonical_dimension="location",
            ),
            build_edit(
                block_id=moisture_block_id,
                column="moisture",
                semantic_role="measure",
                canonical_measure="moisture",
                unit="%",
            ),
        ]
    }


def build_noisy_fixture_edits(block_id: str) -> dict[str, Any]:
    return {
        "columns": [
            build_edit(block_id=block_id, column="date", semantic_role="date"),
            build_edit(block_id=block_id, column="plot_id", semantic_role="dimension", canonical_dimension="plot_id"),
            build_edit(
                block_id=block_id,
                column="yield_kg_ha",
                semantic_role="measure",
                canonical_measure="yield",
                unit="kg/ha",
            ),
            build_edit(
                block_id=block_id,
                column="moisture_pct",
                semantic_role="measure",
                canonical_measure="moisture",
                unit="%",
            ),
            build_edit(block_id=block_id, column="notes", semantic_role="ignore"),
        ]
    }


def upload_snapshot(upload_id: str) -> dict[str, Any]:
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.status,
                    s.artifact_id,
                    s.preview_json,
                    a.original_filename,
                    a.mime_type,
                    a.file_size_bytes,
                    a.file_hash_sha256,
                    a.parser_version,
                    a.sheet_manifest,
                    a.parse_warning_summary,
                    octet_length(a.raw_content) AS raw_content_size
                FROM raw.upload_sessions AS s
                JOIN raw.artifacts AS a ON a.id = s.artifact_id
                WHERE s.id = %s
                """,
                (upload_id,),
            )
            row = cur.fetchone()
    assert row is not None
    return row


def observation_counts(upload_id: str) -> dict[str, int]:
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT count(*) FROM staging.observations WHERE upload_session_id = %s) AS staging_count,
                    (SELECT count(*) FROM harmonized.observations WHERE upload_session_id = %s) AS harmonized_count
                """,
                (upload_id, upload_id),
            )
            row = cur.fetchone()
    assert row is not None
    return {
        "staging": int(row["staging_count"]),
        "harmonized": int(row["harmonized_count"]),
    }


def harmonized_rows(
    *,
    upload_id: str | None = None,
    variable: str | None = None,
    normalized_unit: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if upload_id is not None:
        clauses.append("upload_session_id = %s")
        params.append(upload_id)
    if variable is not None:
        clauses.append("variable = %s")
        params.append(variable)
    if normalized_unit is not None:
        clauses.append("normalized_unit = %s")
        params.append(normalized_unit)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    upload_session_id::text AS upload_session_id,
                    block_id,
                    source_sheet,
                    source_row_index,
                    source_column,
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
                    dimensions_json
                FROM harmonized.observations
                {where_sql}
                ORDER BY upload_session_id, block_id, source_row_index, source_column
                """,
                tuple(params),
            )
            rows = cur.fetchall()
    return rows


@pytest.fixture(scope="session", autouse=True)
def ensure_real_postgres_ready() -> None:
    try:
        with _db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except psycopg.OperationalError as exc:  # pragma: no cover - environment-dependent skip
        pytest.skip(f"Real Postgres e2e validation requires a reachable DATABASE_URL. {exc}")

    subprocess.run([sys.executable, str(MIGRATIONS_SCRIPT)], check=True)


@pytest.fixture(autouse=True)
def clean_real_database() -> None:
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE raw.upload_sessions CASCADE")
            cur.execute("DELETE FROM raw.artifacts")
            cur.execute("DELETE FROM ops.mcp_tool_audit_log")
        conn.commit()
    yield
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE raw.upload_sessions CASCADE")
            cur.execute("DELETE FROM raw.artifacts")
            cur.execute("DELETE FROM ops.mcp_tool_audit_log")
        conn.commit()
