"""Master data CRUD — students, tutors, enrollments, tutor rate versioning.

POST   /students                   — add a student
PUT    /students/{id}              — update name / active flag
GET    /students                   — paginated list
POST   /tutors                     — add a tutor
PUT    /tutors/{id}                — update name / active flag
GET    /tutors                     — paginated list
POST   /tutors/{id}/rates          — add a new rate version (effective_from date)
GET    /tutors/{id}/rates          — rate history for a tutor
POST   /enrollments                — create enrollment
PUT    /enrollments/{id}           — update status / end_date
GET    /enrollments                — paginated list
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.dependencies import db_session, require_cfo, require_session

router = APIRouter(tags=["master-data"])


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


class StudentCreate(BaseModel):
    display_id: str
    name: str


class StudentUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


@router.post("/students", status_code=201)
def create_student(
    payload: StudentCreate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    try:
        row = db.execute(
            text(
                "INSERT INTO master.students (display_id, name) "
                "VALUES (:did, :name) RETURNING student_id"
            ),
            {"did": payload.display_id, "name": payload.name},
        ).one()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"display_id '{payload.display_id}' already exists"
        )
    db.commit()
    return {"student_id": row.student_id, "display_id": payload.display_id, "name": payload.name}


@router.put("/students/{student_id}")
def update_student(
    student_id: int,
    payload: StudentUpdate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    if payload.name is not None:
        db.execute(
            text("UPDATE master.students SET name = :name WHERE student_id = :id"),
            {"id": student_id, "name": payload.name},
        )
    if payload.active is not None:
        db.execute(
            text("UPDATE master.students SET active = :active WHERE student_id = :id"),
            {"id": student_id, "active": payload.active},
        )
    if payload.name is None and payload.active is None:
        raise HTTPException(status_code=400, detail="nothing to update")
    db.commit()
    return {"student_id": student_id, "updated": True}


@router.get("/students")
def list_students(
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            "SELECT student_id, display_id, name, active, created_at "
            "FROM master.students ORDER BY display_id LIMIT :limit OFFSET :skip"
        ),
        {"limit": limit, "skip": skip},
    ).all()
    return {"students": [dict(r._mapping) for r in rows], "limit": limit, "skip": skip}


# ---------------------------------------------------------------------------
# Tutors
# ---------------------------------------------------------------------------


class TutorCreate(BaseModel):
    display_id: str
    name: str
    payment_currency: str = "PKR"


class TutorUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


@router.post("/tutors", status_code=201)
def create_tutor(
    payload: TutorCreate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    try:
        row = db.execute(
            text(
                """
                INSERT INTO master.tutors (display_id, name, payment_currency)
                VALUES (:did, :name, :curr)
                RETURNING tutor_id
                """
            ),
            {"did": payload.display_id, "name": payload.name, "curr": payload.payment_currency},
        ).one()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"display_id '{payload.display_id}' already exists"
        )
    db.commit()
    return {"tutor_id": row.tutor_id, "display_id": payload.display_id, "name": payload.name}


@router.put("/tutors/{tutor_id}")
def update_tutor(
    tutor_id: int,
    payload: TutorUpdate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    if payload.name is not None:
        db.execute(
            text("UPDATE master.tutors SET name = :name WHERE tutor_id = :id"),
            {"id": tutor_id, "name": payload.name},
        )
    if payload.active is not None:
        db.execute(
            text("UPDATE master.tutors SET active = :active WHERE tutor_id = :id"),
            {"id": tutor_id, "active": payload.active},
        )
    if payload.name is None and payload.active is None:
        raise HTTPException(status_code=400, detail="nothing to update")
    db.commit()
    return {"tutor_id": tutor_id, "updated": True}


@router.get("/tutors")
def list_tutors(
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            "SELECT tutor_id, display_id, name, payment_currency, active, created_at "
            "FROM master.tutors ORDER BY display_id LIMIT :limit OFFSET :skip"
        ),
        {"limit": limit, "skip": skip},
    ).all()
    return {"tutors": [dict(r._mapping) for r in rows], "limit": limit, "skip": skip}


# ---------------------------------------------------------------------------
# Tutor rate versioning (reads master.tutor_hour_rates which exists in 0001)
# ---------------------------------------------------------------------------


class TutorRateCreate(BaseModel):
    rate_aed: Decimal
    effective_from: date


@router.post("/tutors/{tutor_id}/rates", status_code=201)
def add_tutor_rate(
    tutor_id: int,
    payload: TutorRateCreate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    if payload.rate_aed <= Decimal("0"):
        raise HTTPException(status_code=400, detail="rate_aed must be > 0")

    # Ensure tutor exists.
    exists = db.execute(
        text("SELECT 1 FROM master.tutors WHERE tutor_id = :id"), {"id": tutor_id}
    ).one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"tutor {tutor_id} not found")

    # Check for exact effective_from overlap (same date).
    conflict = db.execute(
        text(
            "SELECT 1 FROM master.tutor_hour_rates WHERE tutor_id = :id AND effective_from = :from"
        ),
        {"id": tutor_id, "from": payload.effective_from},
    ).one_or_none()
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"rate already set for tutor {tutor_id} effective {payload.effective_from}",
        )

    row = db.execute(
        text(
            """
            INSERT INTO master.tutor_hour_rates (tutor_id, rate_aed, effective_from)
            VALUES (:tid, :rate, :from)
            RETURNING rate_id
            """
        ),
        {"tid": tutor_id, "rate": str(payload.rate_aed), "from": payload.effective_from},
    ).one()
    db.commit()
    return {
        "rate_id": row.rate_id,
        "tutor_id": tutor_id,
        "rate_aed": str(payload.rate_aed),
        "effective_from": payload.effective_from.isoformat(),
    }


@router.get("/tutors/{tutor_id}/rates")
def list_tutor_rates(
    tutor_id: int,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT rate_id, tutor_id, rate_aed::text, effective_from, effective_to, created_at "
            "FROM master.tutor_hour_rates WHERE tutor_id = :id ORDER BY effective_from DESC"
        ),
        {"id": tutor_id},
    ).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------


class EnrollmentCreate(BaseModel):
    student_id: int
    tutor_id: int
    subject: str
    rate_aed: Decimal
    start_date: date
    status: str = "active"


class EnrollmentUpdate(BaseModel):
    status: str | None = None
    end_date: date | None = None


@router.post("/enrollments", status_code=201)
def create_enrollment(
    payload: EnrollmentCreate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    try:
        row = db.execute(
            text(
                """
                INSERT INTO master.enrollments
                    (student_id, tutor_id, subject, rate_aed, start_date, status)
                VALUES (:sid, :tid, :subj, :rate, :sdate, :status)
                RETURNING enrollment_id
                """
            ),
            {
                "sid": payload.student_id,
                "tid": payload.tutor_id,
                "subj": payload.subject,
                "rate": str(payload.rate_aed),
                "sdate": payload.start_date,
                "status": payload.status,
            },
        ).one()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    return {"enrollment_id": row.enrollment_id, "status": payload.status}


@router.put("/enrollments/{enrollment_id}")
def update_enrollment(
    enrollment_id: int,
    payload: EnrollmentUpdate,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    if payload.status is not None:
        db.execute(
            text("UPDATE master.enrollments SET status = :status WHERE enrollment_id = :id"),
            {"id": enrollment_id, "status": payload.status},
        )
    if payload.end_date is not None:
        db.execute(
            text("UPDATE master.enrollments SET end_date = :end_date WHERE enrollment_id = :id"),
            {"id": enrollment_id, "end_date": payload.end_date},
        )
    if payload.status is None and payload.end_date is None:
        raise HTTPException(status_code=400, detail="nothing to update")
    db.commit()
    return {"enrollment_id": enrollment_id, "updated": True}


@router.get("/enrollments")
def list_enrollments(
    student_id: int | None = Query(default=None),
    tutor_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT e.enrollment_id, e.student_id, s.name AS student_name,
                   e.tutor_id, t.name AS tutor_name,
                   e.subject, e.rate_aed::text, e.start_date, e.end_date, e.status
            FROM master.enrollments e
            JOIN master.students s ON s.student_id = e.student_id
            JOIN master.tutors t ON t.tutor_id = e.tutor_id
            WHERE (:student_id IS NULL OR e.student_id = :student_id)
              AND (:tutor_id IS NULL OR e.tutor_id = :tutor_id)
            ORDER BY e.enrollment_id DESC
            LIMIT :limit OFFSET :skip
            """
        ),
        {"student_id": student_id, "tutor_id": tutor_id, "limit": limit, "skip": skip},
    ).all()
    return {"enrollments": [dict(r._mapping) for r in rows], "limit": limit, "skip": skip}
