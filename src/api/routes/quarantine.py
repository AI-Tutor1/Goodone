"""Data quarantine management endpoints.

GET  /quarantine                         — list quarantine records with filters
POST /quarantine/{id}/resolve            — mark as resolved with a note
POST /quarantine/{id}/reprocess          — re-validate and attempt to re-post the row
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import db_session, require_session

router = APIRouter(prefix="/quarantine", tags=["quarantine"])


class ResolvePayload(BaseModel):
    resolution: str


@router.get("")
def list_quarantine(
    source: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default="OPEN"),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT quarantine_id, source, source_ref, severity, status,
                   raw_row, error_detail, resolution, created_at, resolved_at
            FROM staging.data_quality_quarantine
            WHERE (:source IS NULL OR source = :source)
              AND (:severity IS NULL OR severity = :severity)
              AND (:status IS NULL OR status = :status)
            ORDER BY quarantine_id DESC
            LIMIT :limit OFFSET :skip
            """
        ),
        {
            "source": source,
            "severity": severity,
            "status": status,
            "limit": limit,
            "skip": skip,
        },
    ).all()
    return {
        "records": [dict(r._mapping) for r in rows],
        "limit": limit,
        "skip": skip,
    }


@router.post("/{quarantine_id}/resolve")
def resolve_quarantine(
    quarantine_id: int,
    payload: ResolvePayload,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    row = db.execute(
        text(
            "SELECT quarantine_id, status FROM staging.data_quality_quarantine "
            "WHERE quarantine_id = :id"
        ),
        {"id": quarantine_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"quarantine record {quarantine_id} not found")
    if row.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="already resolved")

    db.execute(
        text(
            """
            UPDATE staging.data_quality_quarantine
            SET status = 'RESOLVED', resolution = :res, resolved_at = now()
            WHERE quarantine_id = :id
            """
        ),
        {"id": quarantine_id, "res": payload.resolution},
    )
    db.commit()
    return {"quarantine_id": quarantine_id, "status": "RESOLVED"}


@router.post("/{quarantine_id}/reprocess")
def reprocess_quarantine(
    quarantine_id: int,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    """Re-validate the raw row. If it passes, marks as RESOLVED; otherwise updates error_detail."""
    row = db.execute(
        text(
            "SELECT quarantine_id, source, raw_row, status "
            "FROM staging.data_quality_quarantine WHERE quarantine_id = :id"
        ),
        {"id": quarantine_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"quarantine record {quarantine_id} not found")
    if row.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="already resolved")

    import json

    raw = row.raw_row if isinstance(row.raw_row, dict) else json.loads(row.raw_row or "{}")
    source = row.source or ""

    # Attempt source-specific reprocessing.
    error: str | None = None
    if source in ("lms", "sessions"):
        from src.ingestion.lms import REQUIRED_SESSION_COLUMNS, VALID_STATUSES

        missing = REQUIRED_SESSION_COLUMNS - set(raw.keys())
        if missing:
            error = f"missing columns: {missing}"
        elif raw.get("status") not in VALID_STATUSES:
            error = f"invalid status: {raw.get('status')}"
    else:
        error = f"no reprocessor registered for source '{source}'"

    if error:
        db.execute(
            text(
                "UPDATE staging.data_quality_quarantine "
                "SET error_detail = :err WHERE quarantine_id = :id"
            ),
            {"id": quarantine_id, "err": error},
        )
        db.commit()
        return {"quarantine_id": quarantine_id, "result": "still_invalid", "error": error}

    db.execute(
        text(
            """
            UPDATE staging.data_quality_quarantine
            SET status = 'RESOLVED', resolution = 'reprocessed successfully', resolved_at = now()
            WHERE quarantine_id = :id
            """
        ),
        {"id": quarantine_id},
    )
    db.commit()
    return {"quarantine_id": quarantine_id, "result": "resolved"}
