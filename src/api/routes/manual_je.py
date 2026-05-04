"""CFO manual journal entry endpoint."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import db_session, require_cfo, require_session
from src.core.exceptions import LedgerError
from src.ledger.coa import get_active_coa
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    post_journal,
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
    attachment_url: str | None = None
    attachment_override_reason: str | None = None
    lines: list[LinePayload]


@router.post("")
def post_manual(
    payload: JournalPayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    draft = JournalEntryDraft(
        date=payload.date,
        narration=payload.narration,
        source=f"manual:{session.user_id}",
        source_kind="manual",
        posted_by=session.user_id,
        attachment_url=payload.attachment_url,
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
    return {
        "je_id": posted.je_id,
        "date": str(posted.date),
        "period": posted.period,
        "total_aed": str(posted.total_aed),
        "line_ids": posted.line_ids,
    }


_ = require_session  # symbol kept for future role widening
