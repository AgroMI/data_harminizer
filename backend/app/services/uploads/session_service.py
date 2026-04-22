from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from psycopg import Cursor
from psycopg.types.json import Json

from backend.app.db import get_conn
from backend.app.services.preview_service import parse_upload_source
from backend.app.services.uploads.common import (
    DEFAULT_STORAGE_TYPE,
    DEFAULT_UPLOADER_USER_ID,
    PreviewPayload,
    UPLOAD_STATUS_PREVIEW_READY,
    coerce_string_list,
    sha256_hex,
    strip_internal_preview_fields,
)
from backend.app.services.uploads.preview_service import ensure_preview_mapping_defaults

INSERT_UPLOAD_SQL = """
INSERT INTO raw.upload_sessions (
    id, uploader_user_id, status, original_filename, artifact_id, preview_json
) VALUES (%s, %s, %s, %s, %s, %s)
"""

INSERT_ARTIFACT_SQL = """
INSERT INTO raw.artifacts (
    id,
    original_filename,
    mime_type,
    file_size_bytes,
    file_hash_sha256,
    uploaded_at,
    parser_version,
    storage_type,
    storage_path,
    raw_content,
    sheet_manifest,
    preview_generated_at,
    parse_warning_summary
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

SELECT_UPLOAD_DETAIL_SQL = """
SELECT
    s.id,
    s.status,
    s.preview_json,
    a.id AS artifact_id,
    a.original_filename,
    a.mime_type,
    a.file_size_bytes,
    a.file_hash_sha256,
    a.uploaded_at,
    a.parser_version,
    a.storage_type,
    a.storage_path,
    a.sheet_manifest,
    a.preview_generated_at,
    a.parse_warning_summary
FROM raw.upload_sessions AS s
LEFT JOIN raw.artifacts AS a ON a.id = s.artifact_id
WHERE s.id = %s
"""


def create_upload_session(*, file_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
    upload_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc)

    try:
        parsed_upload = parse_upload_source(file_bytes=file_bytes, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview_json = parsed_upload["preview"]
    ensure_preview_mapping_defaults(preview_json)
    raw_artifact = build_raw_artifact_metadata(
        artifact_id=artifact_id,
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        parsed_upload=parsed_upload,
        uploaded_at=uploaded_at,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                INSERT_ARTIFACT_SQL,
                (
                    artifact_id,
                    filename,
                    mime_type,
                    raw_artifact["file_size_bytes"],
                    raw_artifact["file_hash_sha256"],
                    uploaded_at,
                    raw_artifact["parser_version"],
                    raw_artifact["storage_type"],
                    raw_artifact["storage_path"],
                    file_bytes,
                    Json(raw_artifact["sheet_manifest"]),
                    raw_artifact["preview_generated_at"],
                    Json(raw_artifact["parse_warning_summary"]),
                ),
            )
            cur.execute(
                INSERT_UPLOAD_SQL,
                (
                    upload_id,
                    DEFAULT_UPLOADER_USER_ID,
                    UPLOAD_STATUS_PREVIEW_READY,
                    filename,
                    artifact_id,
                    Json(preview_json),
                ),
            )
        conn.commit()

    return {
        "id": upload_id,
        "status": UPLOAD_STATUS_PREVIEW_READY,
        "preview": strip_internal_preview_fields(preview_json),
        "raw_artifact": public_raw_artifact_metadata(raw_artifact),
    }


def get_upload_session(upload_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            row = fetch_upload_detail_row(cur, upload_id)
            preview_json = row.get("preview_json") or {}
            preview_json = preview_json if isinstance(preview_json, dict) else {}
            ensure_preview_mapping_defaults(preview_json)

    return {
        "id": upload_id,
        "status": str(row.get("status") or UPLOAD_STATUS_PREVIEW_READY),
        "preview": strip_internal_preview_fields(preview_json),
        "raw_artifact": artifact_response_from_row(row),
    }


def get_upload_preview(upload_id: str) -> dict[str, Any]:
    detail = get_upload_session(upload_id)
    return {
        "id": detail["id"],
        "preview": detail["preview"],
        "raw_artifact": detail["raw_artifact"],
    }


def fetch_upload_detail_row(cur: Cursor[Any], upload_id: str) -> dict[str, Any]:
    cur.execute(SELECT_UPLOAD_DETAIL_SQL, (upload_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Upload session {upload_id!r} not found — it may have been deleted or the ID is wrong.")
    return row


def build_raw_artifact_metadata(
    *,
    artifact_id: str,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    parsed_upload: dict[str, Any],
    uploaded_at: datetime,
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "original_filename": filename,
        "mime_type": mime_type,
        "file_size_bytes": len(file_bytes),
        "file_hash_sha256": sha256_hex(file_bytes),
        "uploaded_at": uploaded_at,
        "parser_version": str(parsed_upload.get("parser_version") or "unknown"),
        "storage_type": DEFAULT_STORAGE_TYPE,
        "storage_path": None,
        "sheet_manifest": parsed_upload.get("sheet_manifest", []),
        "preview_generated_at": parsed_upload.get("preview_generated_at"),
        "parse_warning_summary": coerce_string_list(parsed_upload.get("parse_warning_summary")),
    }


def public_raw_artifact_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None

    return {
        "id": metadata.get("id"),
        "original_filename": metadata.get("original_filename"),
        "mime_type": metadata.get("mime_type"),
        "file_size_bytes": metadata.get("file_size_bytes"),
        "file_hash_sha256": metadata.get("file_hash_sha256"),
        "uploaded_at": metadata.get("uploaded_at"),
        "parser_version": metadata.get("parser_version"),
        "storage_type": metadata.get("storage_type"),
        "storage_path": metadata.get("storage_path"),
        "preview_generated_at": metadata.get("preview_generated_at"),
        "sheet_manifest": metadata.get("sheet_manifest", []),
        "parse_warning_summary": metadata.get("parse_warning_summary", []),
    }


def artifact_response_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    artifact_id = row.get("artifact_id")
    if artifact_id is None:
        return None

    return public_raw_artifact_metadata(
        {
            "id": str(artifact_id),
            "original_filename": row.get("original_filename"),
            "mime_type": row.get("mime_type"),
            "file_size_bytes": row.get("file_size_bytes"),
            "file_hash_sha256": row.get("file_hash_sha256"),
            "uploaded_at": row.get("uploaded_at"),
            "parser_version": row.get("parser_version"),
            "storage_type": row.get("storage_type"),
            "storage_path": row.get("storage_path"),
            "preview_generated_at": row.get("preview_generated_at"),
            "sheet_manifest": row.get("sheet_manifest", []),
            "parse_warning_summary": coerce_string_list(row.get("parse_warning_summary")),
        }
    )
