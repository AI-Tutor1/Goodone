"""Bulk data ingestion endpoints.

POST /ingestion/sessions              — upload CSV or XLSX of sessions
POST /ingestion/sessions/google-sheets — pull sessions from a Google Sheet
POST /ingestion/enrollments           — upload CSV or XLSX of enrollments
POST /ingestion/bank-statement        — upload bank CSV for cash reconciliation
GET  /ingestion/lms/sync-status       — last N LMS polling runs
POST /ingestion/lms/sync-now          — trigger an immediate LMS poll

All session uploads share the same idempotency guarantee: a partial unique
index on ledger.journal_entries(source_ref WHERE source_ref IS NOT NULL)
means re-uploading the same session_id is a safe no-op (counted as skipped).
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import db_session, require_session
from src.core.config import get_settings
from src.core.exceptions import LedgerError
from src.core.logging import get_logger
from src.ingestion.bank import BankColumnMap, BankCsvParseError, parse_bank_csv
from src.ingestion.lms import SessionPayload, parse_session_row
from src.ingestion.manual_upload import batch_id, parse_csv

logger = get_logger("ingestion")

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_BANK_MAP = BankColumnMap(
    date="Date",
    amount="Amount",
    description="Description",
    balance="Balance",
    reference="Reference",
)


def _read_file_rows(file: UploadFile, content: bytes) -> list[dict[str, str]]:
    """Parse CSV or XLSX bytes into a list of row dicts. Auto-detect by extension."""
    name = (file.filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            import openpyxl  # type: ignore[import-untyped]
        except ImportError as exc:
            raise HTTPException(
                status_code=400, detail="openpyxl not installed; upload CSV instead"
            ) from exc
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = list(ws.iter_rows(values_only=True))
        if not rows_iter:
            return []
        header = [str(c).strip().lower() if c is not None else "" for c in rows_iter[0]]
        result = []
        for row in rows_iter[1:]:
            result.append(
                {header[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)}
            )
        return result
    # Default: CSV
    text_content = content.decode("utf-8-sig", errors="replace")
    return list(parse_csv(text_content))


def _period_for_date(occurred_on: str) -> str:
    return occurred_on[:7]  # "YYYY-MM-DD"[:7] = "YYYY-MM"


def _insert_upload_record(db, batch: str, source_kind: str, filename: str, uploaded_by: str) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO staging.manual_uploads
                (batch_id, source_kind, filename, uploaded_by, status)
            VALUES (:batch_id, :source_kind, :filename, :uploaded_by, 'processing')
            RETURNING upload_id
            """
        ),
        {
            "batch_id": batch,
            "source_kind": source_kind,
            "filename": filename,
            "uploaded_by": uploaded_by,
        },
    ).one()
    db.commit()
    return row.upload_id


def _finalise_upload(
    db, upload_id: int, accepted: int, skipped: int, quarantined: int, status: str = "done"
) -> None:
    db.execute(
        text(
            """
            UPDATE staging.manual_uploads
            SET accepted = :accepted, skipped = :skipped,
                quarantined = :quarantined,
                row_count = :row_count, status = :status
            WHERE upload_id = :upload_id
            """
        ),
        {
            "accepted": accepted,
            "skipped": skipped,
            "quarantined": quarantined,
            "row_count": accepted + skipped + quarantined,
            "status": status,
            "upload_id": upload_id,
        },
    )
    db.commit()


def _quarantine_row(db, source: str, batch: str, raw: dict, errors: list[str]) -> None:
    db.execute(
        text(
            """
            INSERT INTO staging.data_quality_quarantine
                (source, batch_id, raw_payload, validation_errors)
            VALUES (:source, :batch_id, :raw::jsonb, :errors::jsonb)
            """
        ),
        {
            "source": source,
            "batch_id": batch,
            "raw": str(raw).replace("'", '"'),
            "errors": str(errors).replace("'", '"'),
        },
    )


def _session_already_posted(db, session_id: str) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM ledger.journal_entries "
            "WHERE source_ref = :ref LIMIT 1"
        ),
        {"ref": f"SES-{session_id}-REV"},
    ).one_or_none()
    return row is not None


def _post_session(db, payload: SessionPayload, actor: str) -> tuple[int | None, int | None]:
    """Post revenue + payroll JEs for one session. Returns (revenue_je_id, payroll_je_id).

    Imports lazily to avoid circular deps at module load time.
    """
    from decimal import Decimal

    from src.agents.payroll import (
        PayrollContext,
        build_accrual_draft,
        compute_payment,
    )
    from src.agents.revenue import build_revenue_draft
    from src.core.money import ZERO_AED
    from src.ledger.coa import get_active_coa
    from src.ledger.posting import post_journal
    from src.ledger.subledger import build_default_registry

    coa = get_active_coa()
    registry = build_default_registry()
    period = _period_for_date(payload.occurred_on)
    posting_date = date.fromisoformat(payload.occurred_on)

    # Look up enrollment → student_id, tutor_id, student_rate, tutor_rate
    enr = db.execute(
        text(
            """
            SELECT e.student_id, e.tutor_id, e.subject, e.grade, e.curriculum,
                   COALESCE(
                     (SELECT rate_aed FROM master.student_hour_rates
                      WHERE subject = e.subject AND grade = e.grade
                        AND curriculum = e.curriculum
                        AND effective_from <= :occ
                        AND (effective_to IS NULL OR effective_to > :occ)
                      ORDER BY effective_from DESC LIMIT 1), 0
                   ) AS student_rate_aed,
                   COALESCE(
                     (SELECT rate_aed FROM master.tutor_hour_rates
                      WHERE tutor_id = e.tutor_id AND subject = e.subject
                        AND grade = e.grade AND curriculum = e.curriculum
                        AND effective_from <= :occ
                        AND (effective_to IS NULL OR effective_to > :occ)
                      ORDER BY effective_from DESC LIMIT 1), 0
                   ) AS tutor_rate_aed,
                   t.payment_currency
            FROM master.enrollments e
            JOIN master.tutors t ON t.tutor_id = e.tutor_id
            WHERE e.enrollment_id = :eid
            """
        ),
        {"eid": payload.enrollment_id, "occ": payload.occurred_on},
    ).one_or_none()

    if enr is None:
        raise ValueError(f"enrollment_id {payload.enrollment_id} not found")

    # Look up FX rate for that day (PKR tutors)
    fx_rate = Decimal("1")
    if enr.payment_currency == "PKR":
        fx_row = db.execute(
            text(
                "SELECT rate FROM master.fx_rates "
                "WHERE base = 'AED' AND quote = 'PKR' AND date <= :d "
                "ORDER BY date DESC LIMIT 1"
            ),
            {"d": payload.occurred_on},
        ).one_or_none()
        if fx_row:
            fx_rate = Decimal(str(fx_row.rate))

    revenue_je_id: int | None = None
    payroll_je_id: int | None = None

    # Revenue JE
    if enr.student_rate_aed and Decimal(str(enr.student_rate_aed)) > ZERO_AED:
        rev_draft = build_revenue_draft(
            session_id=payload.session_id,
            enrollment_id=payload.enrollment_id,
            student_id=enr.student_id,
            status=payload.status,
            student_rate_aed=Decimal(str(enr.student_rate_aed)),
            scheduled_minutes=payload.scheduled_minutes,
            conducted_minutes=payload.conducted_minutes,
            posting_date=posting_date,
            period=period,
        )
        if rev_draft:
            posted_rev = post_journal(db, rev_draft, coa=coa, sub_ledgers=registry)
            revenue_je_id = posted_rev.je_id

    # Payroll JE
    if payload.status != "student_absent" and payload.conducted_minutes > 0:
        tutor_rate = Decimal(str(enr.tutor_rate_aed))
        comp = compute_payment(
            tutor_rate_aed=tutor_rate,
            scheduled_minutes=payload.scheduled_minutes,
            conducted_minutes=payload.conducted_minutes,
        )
        ctx = PayrollContext(
            session_id=payload.session_id,
            enrollment_id=payload.enrollment_id,
            tutor_id=enr.tutor_id,
            posting_date=posting_date,
            fx_rate_aed_to_pkr=fx_rate,
            period=period,
        )
        pay_draft = build_accrual_draft(ctx, comp)
        if pay_draft:
            posted_pay = post_journal(db, pay_draft, coa=coa, sub_ledgers=registry)
            payroll_je_id = posted_pay.je_id

    # Persist session record
    db.execute(
        text(
            """
            INSERT INTO master.sessions
                (session_id, enrollment_id, scheduled_minutes, conducted_minutes,
                 status, occurred_on, period, revenue_je_id, payroll_je_id)
            VALUES (:sid, :eid, :sched, :cond, :status, :occ, :period, :rev, :pay)
            ON CONFLICT (session_id) DO NOTHING
            """
        ),
        {
            "sid": payload.session_id,
            "eid": payload.enrollment_id,
            "sched": payload.scheduled_minutes,
            "cond": payload.conducted_minutes,
            "status": payload.status,
            "occ": payload.occurred_on,
            "period": period,
            "rev": revenue_je_id,
            "pay": payroll_je_id,
        },
    )
    return revenue_je_id, payroll_je_id


def _process_session_rows(
    rows: list[dict[str, str]],
    db,
    actor: str,
    batch: str,
) -> tuple[int, int, int, list[dict]]:
    """Returns (accepted, skipped, quarantined, error_list)."""
    accepted = skipped = quarantined = 0
    errors: list[dict] = []

    for i, row in enumerate(rows):
        try:
            payload = parse_session_row(row)
        except ValueError as exc:
            _quarantine_row(db, "sessions", batch, row, [str(exc)])
            db.commit()
            quarantined += 1
            errors.append({"row": i + 2, "error": str(exc)})
            continue

        if _session_already_posted(db, payload.session_id):
            skipped += 1
            continue

        try:
            _post_session(db, payload, actor)
            db.commit()
            accepted += 1
        except (LedgerError, ValueError, IntegrityError) as exc:
            db.rollback()
            msg = getattr(exc, "message", str(exc))
            _quarantine_row(db, "sessions", batch, row, [msg])
            db.commit()
            quarantined += 1
            errors.append({"row": i + 2, "session_id": row.get("session_id"), "error": msg})

    return accepted, skipped, quarantined, errors


# ---------------------------------------------------------------------------
# Session upload endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions")
async def upload_sessions(
    file: UploadFile,
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Upload a CSV or XLSX of sessions. Idempotent — duplicate session_ids are skipped."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    rows = _read_file_rows(file, content)
    if not rows:
        raise HTTPException(status_code=400, detail="file contains no data rows")

    batch = batch_id(content.decode("utf-8-sig", errors="replace"), source="sessions")
    upload_id = _insert_upload_record(
        db, batch, "sessions", file.filename or "upload", session.user_id
    )

    accepted, skipped, quarantined, errors = _process_session_rows(rows, db, session.user_id, batch)
    _finalise_upload(db, upload_id, accepted, skipped, quarantined)

    logger.info(
        "session_upload_complete",
        upload_id=upload_id,
        accepted=accepted,
        skipped=skipped,
        quarantined=quarantined,
        actor=session.user_id,
    )
    return {
        "upload_id": upload_id,
        "accepted": accepted,
        "skipped": skipped,
        "quarantined": quarantined,
        "errors": errors[:20],  # cap error list returned to client
    }


class GoogleSheetsSessionBody(BaseModel):
    spreadsheet_id: str
    tab_name: str = "sessions"


@router.post("/sessions/google-sheets")
def upload_sessions_from_sheets(
    body: GoogleSheetsSessionBody,
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Pull sessions from a Google Sheet tab and run the same ingestion pipeline."""
    settings = get_settings()
    if not settings.google_service_account_json_path:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_SERVICE_ACCOUNT_JSON_PATH is not configured",
        )
    from src.ingestion.sheets import GenericSheetsAdapter
    adapter = GenericSheetsAdapter(
        sa_json_path=settings.google_service_account_json_path,
        spreadsheet_id=body.spreadsheet_id,
    )
    try:
        rows = adapter.fetch_rows(body.tab_name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets error: {exc}") from exc

    if not rows:
        return {"accepted": 0, "skipped": 0, "quarantined": 0, "errors": []}

    batch = batch_id(str(rows), source=f"sheets:{body.spreadsheet_id}")
    upload_id = _insert_upload_record(
        db, batch, "sessions", f"sheets:{body.tab_name}", session.user_id
    )
    accepted, skipped, quarantined, errors = _process_session_rows(rows, db, session.user_id, batch)
    _finalise_upload(db, upload_id, accepted, skipped, quarantined)
    return {
        "upload_id": upload_id,
        "accepted": accepted,
        "skipped": skipped,
        "quarantined": quarantined,
        "errors": errors[:20],
    }


# ---------------------------------------------------------------------------
# Enrollment upload
# ---------------------------------------------------------------------------

REQUIRED_ENROLLMENT_COLUMNS = {
    "student_id", "tutor_id", "subject", "grade", "curriculum", "start_date"
}


@router.post("/enrollments")
async def upload_enrollments(
    file: UploadFile,
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Upload a CSV or XLSX of enrollments. Upserts: creates if new, skips if existing."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    rows = _read_file_rows(file, content)
    if not rows:
        raise HTTPException(status_code=400, detail="file contains no data rows")

    batch = batch_id(content.decode("utf-8-sig", errors="replace"), source="enrollments")
    upload_id = _insert_upload_record(
        db, batch, "enrollments", file.filename or "upload", session.user_id
    )

    accepted = skipped = quarantined = 0
    errors: list[dict] = []

    for i, row in enumerate(rows):
        missing = REQUIRED_ENROLLMENT_COLUMNS - set(row.keys())
        if missing:
            _quarantine_row(db, "enrollments", batch, row, [f"missing columns: {missing}"])
            db.commit()
            quarantined += 1
            errors.append({"row": i + 2, "error": f"missing columns: {missing}"})
            continue

        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO master.enrollments
                        (student_id, tutor_id, subject, grade, curriculum,
                         start_date, end_date, status)
                    VALUES
                        (:student_id, :tutor_id, :subject, :grade, :curriculum,
                         :start_date, :end_date, :status)
                    ON CONFLICT DO NOTHING
                    RETURNING enrollment_id
                    """
                ),
                {
                    "student_id": int(row["student_id"]),
                    "tutor_id": int(row["tutor_id"]),
                    "subject": row["subject"].strip(),
                    "grade": row.get("grade", "").strip(),
                    "curriculum": row.get("curriculum", "").strip(),
                    "start_date": row["start_date"].strip(),
                    "end_date": row.get("end_date") or None,
                    "status": row.get("status", "active").strip().lower(),
                },
            ).one_or_none()
            db.commit()
            if result is None:
                skipped += 1
            else:
                accepted += 1
        except Exception as exc:
            db.rollback()
            msg = str(exc)
            _quarantine_row(db, "enrollments", batch, row, [msg])
            db.commit()
            quarantined += 1
            errors.append({"row": i + 2, "error": msg})

    _finalise_upload(db, upload_id, accepted, skipped, quarantined)
    return {
        "upload_id": upload_id,
        "accepted": accepted,
        "skipped": skipped,
        "quarantined": quarantined,
        "errors": errors[:20],
    }


# ---------------------------------------------------------------------------
# Bank statement reconciliation upload
# ---------------------------------------------------------------------------


@router.post("/bank-statement")
async def upload_bank_statement(
    file: UploadFile,
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Upload a bank statement CSV. Matches transactions against GL account 1010
    and returns matched / unmatched counts with a net difference."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    csv_text = content.decode("utf-8-sig", errors="replace")
    try:
        txns = list(parse_bank_csv(csv_text, _DEFAULT_BANK_MAP))
    except BankCsvParseError as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}") from exc

    if not txns:
        raise HTTPException(status_code=400, detail="no transactions found in file")

    # Sum bank movements
    from decimal import Decimal
    bank_total = sum(t.amount_aed for t in txns)

    # Sum GL cash account (1010) movements for the date range in the file
    min_date = min(t.date for t in txns)
    max_date = max(t.date for t in txns)

    gl_row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) AS net_aed
            FROM ledger.journal_lines jl
            JOIN ledger.journal_entries je ON je.je_id = jl.je_id
            WHERE jl.account_code = '1010'
              AND je.date BETWEEN :min_d AND :max_d
              AND je.status = 'POSTED'
            """
        ),
        {"min_d": min_date, "max_d": max_date},
    ).one()

    gl_net = Decimal(str(gl_row.net_aed))
    diff = bank_total - gl_net

    logger.info(
        "bank_statement_reconciliation",
        transactions=len(txns),
        bank_total=str(bank_total),
        gl_net=str(gl_net),
        diff=str(diff),
        actor=session.user_id,
    )
    return {
        "transactions_in_file": len(txns),
        "date_range": {"from": str(min_date), "to": str(max_date)},
        "bank_net_aed": str(bank_total),
        "gl_cash_net_aed": str(gl_net),
        "difference_aed": str(diff),
        "reconciled": diff == Decimal("0"),
    }


# ---------------------------------------------------------------------------
# LMS sync status + manual trigger
# ---------------------------------------------------------------------------


@router.get("/lms/sync-status")
def lms_sync_status(
    limit: int = Query(default=20, le=100),
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Return the last N LMS polling runs."""
    rows = db.execute(
        text(
            """
            SELECT sync_id, started_at, completed_at, since_date,
                   sessions_fetched, sessions_posted, sessions_skipped,
                   sessions_quarantined, status, error
            FROM staging.lms_sync_log
            ORDER BY sync_id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).all()
    return {
        "syncs": [
            {
                "sync_id": r.sync_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "since_date": str(r.since_date),
                "sessions_fetched": r.sessions_fetched,
                "sessions_posted": r.sessions_posted,
                "sessions_skipped": r.sessions_skipped,
                "sessions_quarantined": r.sessions_quarantined,
                "status": r.status,
                "error": r.error,
            }
            for r in rows
        ]
    }


@router.post("/lms/sync-now")
def lms_sync_now(
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    """Trigger an immediate LMS poll. Uses the date of the last successful sync
    as the ``since`` parameter; falls back to 30 days ago if no prior sync."""
    settings = get_settings()
    if not settings.lms_api_base_url:
        raise HTTPException(
            status_code=503,
            detail="LMS_API_BASE_URL is not configured",
        )

    # Determine since_date from last successful sync
    last = db.execute(
        text(
            "SELECT since_date FROM staging.lms_sync_log "
            "WHERE status = 'done' ORDER BY sync_id DESC LIMIT 1"
        )
    ).one_or_none()
    from datetime import timedelta
    since_date: date = last.since_date if last else (date.today() - timedelta(days=30))

    # Insert sync log record
    sync_row = db.execute(
        text(
            "INSERT INTO staging.lms_sync_log (since_date) VALUES (:d) RETURNING sync_id"
        ),
        {"d": since_date},
    ).one()
    sync_id = sync_row.sync_id
    db.commit()

    from src.ingestion.lms import LmsHttpAdapter
    adapter = LmsHttpAdapter(
        base_url=settings.lms_api_base_url,
        api_key=settings.lms_api_key.get_secret_value() if settings.lms_api_key else "",
    )

    try:
        payloads = list(adapter.fetch_sessions(str(since_date)))
    except Exception as exc:
        db.execute(
            text(
                "UPDATE staging.lms_sync_log SET status='failed', error=:e, "
                "completed_at=now() WHERE sync_id=:id"
            ),
            {"e": str(exc), "id": sync_id},
        )
        db.commit()
        raise HTTPException(status_code=502, detail=f"LMS fetch failed: {exc}") from exc

    batch = f"lms:sync:{sync_id}"
    accepted, skipped, quarantined, _ = _process_session_rows(
        [
            {
                "session_id": p.session_id,
                "enrollment_id": str(p.enrollment_id),
                "scheduled_minutes": str(p.scheduled_minutes),
                "conducted_minutes": str(p.conducted_minutes),
                "status": p.status,
                "occurred_on": p.occurred_on,
            }
            for p in payloads
        ],
        db,
        session.user_id,
        batch,
    )

    db.execute(
        text(
            """
            UPDATE staging.lms_sync_log
            SET status = 'done', completed_at = :now,
                sessions_fetched = :fetched, sessions_posted = :posted,
                sessions_skipped = :skipped, sessions_quarantined = :quar
            WHERE sync_id = :id
            """
        ),
        {
            "now": datetime.now(timezone.utc),
            "fetched": len(payloads),
            "posted": accepted,
            "skipped": skipped,
            "quar": quarantined,
            "id": sync_id,
        },
    )
    db.commit()
    return {
        "sync_id": sync_id,
        "since_date": str(since_date),
        "sessions_fetched": len(payloads),
        "sessions_posted": accepted,
        "sessions_skipped": skipped,
        "sessions_quarantined": quarantined,
    }
