"""Tutor payout disbursement endpoints.

POST /payroll/disburse
    Upload a CSV or XLSX of (tutor_id, amount_aed, payment_date, bank_ref).
    For each row: posts Dr 2020 / Cr 1010 clearing JE (with tutor_id sub-ledger key),
    records in subledger.tutor_disbursements.

GET  /payroll/disbursement-export?period=YYYY-MM
    Returns a CSV of all tutor payables for the period: tutor name, currency,
    AED amount, PKR amount — ready for bank portal upload.

GET  /payroll/disbursement-history
    Returns posted disbursements with optional ?tutor_id and ?period filters.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import db_session, require_cfo, require_session
from src.core.exceptions import LedgerError
from src.core.logging import get_logger
from src.ingestion.manual_upload import parse_csv
from src.ledger.coa import get_active_coa
from src.ledger.posting import JournalEntryDraft, JournalLineDraft, post_journal
from src.ledger.subledger import build_default_registry

logger = get_logger("payroll")
router = APIRouter(prefix="/payroll", tags=["payroll"])


def _read_csv_or_xlsx(filename: str, content: bytes) -> list[dict[str, str]]:
    if filename.lower().endswith((".xlsx", ".xls")):
        try:
            import openpyxl  # type: ignore[import-untyped]
        except ImportError as exc:
            raise HTTPException(status_code=400, detail="openpyxl not installed; use CSV") from exc
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = list(ws.iter_rows(values_only=True))
        if not rows_iter:
            return []
        header = [str(c).strip().lower() if c is not None else "" for c in rows_iter[0]]
        return [
            {header[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)}
            for row in rows_iter[1:]
        ]
    text_content = content.decode("utf-8-sig", errors="replace")
    return list(parse_csv(text_content))


@router.post("/disburse")
async def disburse_payroll(
    file: UploadFile,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    """Upload a payout sheet. Each row clears tutor payable (Dr 2020) against cash (Cr 1010)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    rows = _read_csv_or_xlsx(file.filename or "", content)
    if not rows:
        raise HTTPException(status_code=400, detail="no data rows in file")

    required = {"tutor_id", "amount_aed", "payment_date"}
    coa = get_active_coa()
    registry = build_default_registry()

    from decimal import Decimal

    from src.core.money import aed

    disbursed = 0
    total_aed = Decimal("0")
    errors: list[dict] = []

    for i, row in enumerate(rows):
        missing = required - set(row.keys())
        if missing:
            errors.append({"row": i + 2, "error": f"missing columns: {missing}"})
            continue

        try:
            tutor_id = int(row["tutor_id"])
            amount = aed(row["amount_aed"])
            pay_date = date.fromisoformat(row["payment_date"].strip())
        except (ValueError, KeyError) as exc:
            errors.append({"row": i + 2, "error": str(exc)})
            continue

        if amount <= Decimal("0"):
            errors.append({"row": i + 2, "error": "amount_aed must be > 0"})
            continue

        bank_ref = row.get("bank_ref", "").strip() or None

        # Verify tutor exists and get their currency
        tutor = db.execute(
            text("SELECT tutor_id, name, payment_currency FROM master.tutors WHERE tutor_id = :id"),
            {"id": tutor_id},
        ).one_or_none()
        if tutor is None:
            errors.append({"row": i + 2, "error": f"tutor_id {tutor_id} not found"})
            continue

        period = pay_date.strftime("%Y-%m")
        narration = f"Payroll disbursement tutor={tutor_id} date={pay_date}"
        if bank_ref:
            narration += f" ref={bank_ref}"

        draft = JournalEntryDraft(
            date=pay_date,
            narration=narration,
            source="system:payroll_disbursement",
            source_kind="manual",
            posted_by=session.user_id,
            lines=[
                JournalLineDraft(
                    account_code="2020",
                    debit_aed=amount,
                    sub_ledger_keys={"tutor_id": tutor_id},
                ),
                JournalLineDraft(
                    account_code="1010",
                    credit_aed=amount,
                ),
            ],
        )

        try:
            posted = post_journal(db, draft, coa=coa, sub_ledgers=registry)
        except LedgerError as exc:
            db.rollback()
            errors.append({"row": i + 2, "error": exc.message})
            continue
        except IntegrityError as exc:
            db.rollback()
            errors.append({"row": i + 2, "error": str(exc)})
            continue

        # Record disbursement
        db.execute(
            text(
                """
                INSERT INTO subledger.tutor_disbursements
                    (tutor_id, je_id, amount_aed, payment_currency, bank_ref, payment_date, period)
                VALUES (:tid, :je_id, :amt, :curr, :ref, :pdate, :period)
                """
            ),
            {
                "tid": tutor_id,
                "je_id": posted.je_id,
                "amt": str(amount),
                "curr": tutor.payment_currency,
                "ref": bank_ref,
                "pdate": pay_date,
                "period": period,
            },
        )
        db.commit()
        disbursed += 1
        total_aed += amount
        logger.info(
            "payroll_disbursed",
            tutor_id=tutor_id,
            amount_aed=str(amount),
            je_id=posted.je_id,
            actor=session.user_id,
        )

    return {
        "disbursed": disbursed,
        "total_aed": str(total_aed),
        "errors": errors,
    }


@router.get("/disbursement-export")
def disbursement_export(
    period: str = Query(..., description="YYYY-MM"),
    session=Depends(require_session),
    db=Depends(db_session),
) -> StreamingResponse:
    """Export pending tutor payables for the given period as a bank-ready CSV."""
    rows = db.execute(
        text(
            """
            SELECT t.tutor_id, t.display_id, t.name, t.payment_currency,
                   COALESCE(SUM(e.delta_aed), 0)::text          AS amount_aed,
                   COALESCE(SUM(e.original_amount), 0)::text    AS amount_original
            FROM subledger.tutor_payable_entries e
            JOIN master.tutors t ON t.tutor_id = e.tutor_id
            WHERE e.period = :period
            GROUP BY t.tutor_id, t.display_id, t.name, t.payment_currency
            HAVING COALESCE(SUM(e.delta_aed), 0) > 0
            ORDER BY t.display_id
            """
        ),
        {"period": period},
    ).all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "tutor_id", "display_id", "name",
            "payment_currency", "amount_aed", "amount_original",
        ],
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r._mapping))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll-export-{period}.csv"},
    )


@router.get("/disbursement-history")
def disbursement_history(
    tutor_id: int | None = Query(default=None),
    period: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    filters = "WHERE 1=1"
    params: dict = {"limit": limit, "skip": skip}
    if tutor_id is not None:
        filters += " AND d.tutor_id = :tutor_id"
        params["tutor_id"] = tutor_id
    if period is not None:
        filters += " AND d.period = :period"
        params["period"] = period

    rows = db.execute(
        text(
            f"""
            SELECT d.disbursement_id, d.tutor_id, t.name, t.display_id,
                   d.amount_aed::text, d.payment_currency,
                   d.bank_ref, d.payment_date::text, d.period, d.je_id,
                   d.created_at
            FROM subledger.tutor_disbursements d
            JOIN master.tutors t ON t.tutor_id = d.tutor_id
            {filters}
            ORDER BY d.disbursement_id DESC
            LIMIT :limit OFFSET :skip
            """
        ),
        params,
    ).all()

    return {
        "disbursements": [dict(r._mapping) for r in rows],
        "limit": limit,
        "skip": skip,
    }
