"""System administration endpoints.

GET  /system/backups         — list recent backup files with sizes and timestamps
POST /system/backups/trigger — CFO-only; runs scripts/backup.sh and returns stdout
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import require_cfo
from src.core.config import get_settings

router = APIRouter(prefix="/system", tags=["system"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKUP_SCRIPT = _REPO_ROOT / "scripts" / "backup.sh"

_backup_running = False


@router.get("/backups")
def list_backups(session=Depends(require_cfo)) -> dict:
    get_settings()
    backup_dir = Path(os.environ.get("BACKUP_DIR", str(_REPO_ROOT / "backups")))
    if not backup_dir.exists():
        return {"backups": [], "backup_dir": str(backup_dir)}

    files = sorted(backup_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:20]
    return {
        "backup_dir": str(backup_dir),
        "backups": [
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified_at": f.stat().st_mtime,
            }
            for f in files
            if f.is_file()
        ],
    }


@router.post("/backups/trigger")
def trigger_backup(session=Depends(require_cfo)) -> dict:
    global _backup_running
    if _backup_running:
        raise HTTPException(status_code=409, detail="a backup is already running")
    if not _BACKUP_SCRIPT.exists():
        raise HTTPException(status_code=503, detail="backup script not found")

    _backup_running = True
    try:
        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(_BACKUP_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="backup script timed out after 300 s")
    finally:
        _backup_running = False

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"error": "backup script failed", "stderr": result.stderr[-2000:]},
        )
    return {
        "ok": True,
        "stdout": result.stdout[-4000:],
        "returncode": result.returncode,
    }
