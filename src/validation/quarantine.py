"""Quarantine helper.

Bad ingestion rows are inserted into ``staging.data_quality_quarantine``
with the full raw payload + a list of validation errors so a human (or the
re-ingest CLI) can resolve them later.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.validation.rules import RuleResult


def quarantine(
    session: Session,
    *,
    source: str,
    batch_id: str,
    payload: dict,
    errors: list[RuleResult],
    affected_period: str | None = None,
) -> int:
    """Insert one quarantine row and return its id."""
    return int(
        session.execute(
            text(
                """
                INSERT INTO staging.data_quality_quarantine (
                    source, batch_id, raw_payload, validation_errors,
                    affected_period, created_at, status
                ) VALUES (
                    :source, :batch_id,
                    CAST(:payload AS jsonb), CAST(:errors AS jsonb),
                    :period, NOW(), 'OPEN'
                ) RETURNING id
                """,
            ),
            {
                "source": source,
                "batch_id": batch_id,
                "payload": json.dumps(payload, default=str),
                "errors": json.dumps(
                    [
                        {
                            "code": e.code,
                            "message": e.message,
                            "field": e.field,
                        }
                        for e in errors
                    ],
                ),
                "period": affected_period,
            },
        ).scalar_one(),
    )


def open_count(session: Session, *, period: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM staging.data_quality_quarantine WHERE status='OPEN'"
    params: dict[str, object] = {}
    if period:
        sql += " AND affected_period = :p"
        params["p"] = period
    return int(session.execute(text(sql), params).scalar_one())


def resolve(session: Session, qid: int, *, by: str, notes: str) -> None:
    session.execute(
        text(
            "UPDATE staging.data_quality_quarantine "
            "SET status='RESOLVED', resolved_at=NOW(), "
            "    resolved_by=:by, resolution_notes=:notes "
            "WHERE id = :id",
        ),
        {"id": qid, "by": by, "notes": notes},
    )
