"""CFO manual journal entry endpoint.

POST /journal          — post a new manual JE
POST /journal/{id}/reverse — reverse a posted JE (Bug #26 fix: previously missing)

Attachment policy (enforced by DB CHECK + step 8 of posting validation):
  total_aed > 50,000 and source_kind='manual' requires either:
  - attachment_id referencing a real file in staging.attachments, OR
  - attachment_override_reason of ≥ 30 chars

The attachment_id field replaces the old free-text attachment_url so the
policy is actually enforceable — callers must upload via POST /uploads first.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.api.dependencies import db_session, require_cfo, require_session
from src.core.exceptions import LedgerError
from src.ledger.coa import get_active_coa
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    post_journal,
    reverse_journal,
)
from src.ledger.subledger import build_default_registry

router = APIRouter(prefix="/journal", tags=["journal"])


class LinePayload(BaseModel):
    account_code: str
    debit_aed: Decimal = Decimal("0")
    credit_aed: Decimal = Decimal("0")
    sub_ledger_keys: dict[str, str | int] = {}
    dimensions: dict[str, str | int] = {}


class JournalPayload(BaseModel):
    date: date
    narration: str
    # Use attachment_id (from POST /uploads) instead of free-text URL.
    # The actual stored_path is looked up server-side so the policy is enforceable.
    attachment_id: int | None = None
    attachment_override_reason: str | None = None
    lines: list[LinePayload]


class ReversePayload(BaseModel):
    narration: str = ""
    on_date: date | None = None


def _resolve_attachment_url(attachment_id: int | None, db) -> str | None:
    if attachment_id is None:
        return None
    row = db.execute(
        text(
            "SELECT stored_path FROM staging.attachments WHERE attachment_id = :id"
        ),
        {"id": attachment_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"attachment_id {attachment_id} not found — upload the file first via POST /uploads",
        )
    return row.stored_path


@router.post("")
def post_manual(
    payload: JournalPayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    attachment_url = _resolve_attachment_url(payload.attachment_id, db)
    draft = JournalEntryDraft(
        date=payload.date,
        narration=payload.narration,
        source=f"manual:{session.user_id}",
        source_kind="manual",
        posted_by=session.user_id,
        attachment_url=attachment_url,
        attachment_override_reason=payload.attachment_override_reason,
        lines=[JournalLineDraft(**line.model_dump()) for line in payload.lines],
    )
    coa = get_active_coa()
    registry = build_default_registry()
    try:
        posted = post_journal(db, draft, coa=coa, sub_ledgers=registry)
    except LedgerError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": type(exc).__name__, "message": exc.message, "context": exc.context},
        ) from None

    # Link the attachment to this JE so it's traceable.
    if payload.attachment_id is not None:
        db.execute(
            text(
                "UPDATE staging.attachments SET linked_je_id = :je_id "
                "WHERE attachment_id = :att_id"
            ),
            {"je_id": posted.je_id, "att_id": payload.attachment_id},
        )
        db.commit()

    return {
        "je_id": posted.je_id,
        "date": str(posted.date),
        "period": posted.period,
        "total_aed": str(posted.total_aed),
        "line_ids": posted.line_ids,
    }


@router.post("/{je_id}/reverse")
def reverse_manual(
    je_id: int,
    payload: ReversePayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    """Reverse a posted JE. The original is marked REVERSED; a new equal-and-
    opposite JE is posted with reverses_je_id pointing back to the original."""
    narration = payload.narration or f"Reversal of JE#{je_id}"
    if len(narration) < 10:
        narration = f"Reversal of JE#{je_id} — {narration}"

    coa = get_active_coa()
    registry = build_default_registry()
    try:
        reversed_je = reverse_journal(
            db,
            je_id,
            narration=narration,
            posted_by=session.user_id,
            coa=coa,
            sub_ledgers=registry,
            on_date=payload.on_date,
        )
    except LedgerError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": type(exc).__name__, "message": exc.message, "context": exc.context},
        ) from None

    return {
        "original_je_id": je_id,
        "reversal_je_id": reversed_je.je_id,
        "date": str(reversed_je.date),
        "period": reversed_je.period,
        "total_aed": str(reversed_je.total_aed),
    }


_ = require_session  # kept for future role widening
