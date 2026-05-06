"""File upload and retrieval.

POST /uploads   — accepts a multipart file, stores it on disk, records metadata
                  in staging.attachments, and returns the attachment_id.
GET  /uploads/{attachment_id} — serves the stored file with original filename.

The stored path is:  ATTACHMENTS_DIR / <sha256[:16]>.<ext>
Using the content hash as the filename makes uploads idempotent: uploading the
same file twice yields the same stored_path with a new staging.attachments row.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import db_session, require_session
from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("uploads")

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "image/",
    "application/vnd.openxmlformats-officedocument.spreadsheetml",  # .xlsx
    "application/vnd.ms-excel",  # .xls
    "text/csv",
    "text/plain",
)


def _allowed(mime: str) -> bool:
    return any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES)


@router.post("")
async def upload_file(
    file: UploadFile,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    settings = get_settings()
    max_bytes = settings.attachments_max_size_mb * 1024 * 1024

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds limit of {settings.attachments_max_size_mb} MB",
        )

    # Detect mime type — prefer the header, fall back to extension sniffing.
    mime = file.content_type or ""
    if not mime or mime == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(file.filename or "")
        mime = guessed or "application/octet-stream"

    if not _allowed(mime):
        raise HTTPException(
            status_code=415,
            detail=f"mime type '{mime}' is not permitted; allowed: pdf, images, xlsx, csv",
        )

    # Deterministic filename from content hash — re-uploading the same file reuses disk space.
    digest = hashlib.sha256(content).hexdigest()[:16]
    suffix = Path(file.filename or "upload").suffix or ".bin"
    stored_name = f"{digest}{suffix}"
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.attachments_dir / stored_name

    if not stored_path.exists():
        stored_path.write_bytes(content)
        logger.info("attachment_written", path=str(stored_path), bytes=len(content))

    row = db.execute(
        text(
            """
            INSERT INTO staging.attachments
                (filename, stored_path, mime_type, size_bytes, uploaded_by)
            VALUES (:filename, :stored_path, :mime_type, :size_bytes, :uploaded_by)
            RETURNING attachment_id
            """
        ),
        {
            "filename": file.filename or stored_name,
            "stored_path": str(stored_path),
            "mime_type": mime,
            "size_bytes": len(content),
            "uploaded_by": session.user_id,
        },
    ).one()
    db.commit()

    attachment_id = row.attachment_id
    logger.info(
        "attachment_registered",
        attachment_id=attachment_id,
        filename=file.filename,
        actor=session.user_id,
    )
    return {
        "attachment_id": attachment_id,
        "filename": file.filename,
        "mime_type": mime,
        "size_bytes": len(content),
        "url": f"/uploads/{attachment_id}",
    }


@router.get("/{attachment_id}")
def download_file(
    attachment_id: int,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> FileResponse:
    row = db.execute(
        text(
            "SELECT filename, stored_path, mime_type "
            "FROM staging.attachments WHERE attachment_id = :id"
        ),
        {"id": attachment_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="attachment not found")

    stored = Path(row.stored_path)
    if not stored.exists():
        raise HTTPException(status_code=404, detail="attachment file missing from disk")

    return FileResponse(
        path=str(stored),
        media_type=row.mime_type,
        filename=row.filename,
    )
