"""Tuitional Finance — FastAPI app.

Phase 5 surface. The app loads the COA from ``docs/chart_of_accounts.yaml``
on startup and exposes:

* ``/auth/login``, ``/auth/logout``, ``/auth/me``
* ``/coa``, ``/coa/{code}``                           (public health + spec)
* ``/db/health``                                      (Postgres ping)
* ``/reports/pnl/{period}``, ``/reports/bs``, ``/reports/kpis/{period}``,
  ``/reports/profitability``
* ``/subledgers/wallets``, ``/subledgers/tutor-payables``,
  ``/subledgers/fixed-assets``, ``/subledgers/prepaids``
* ``/journal``                                         (CFO manual JE)
* ``/sanctions``, ``/sanctions/{id}/fa-decide``,
  ``/sanctions/{id}/cfo-decide``, ``/sanctions/{id}/spend``
* ``/periods``, ``/periods/{p}/pre-close``, ``/periods/{p}/close``,
  ``/periods/{p}/reopen``
* ``/fx/rates``, ``/fx/override``
* ``/reconcile``                                       (sub-ledger ↔ GL)

Run via ``make api`` (port 3002 by default).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.dependencies import db_session, require_session
from src.api.observability import ObservabilityMiddleware, render_prometheus
from src.api.routes import auth as auth_routes
from src.api.routes import budget as budget_routes
from src.api.routes import chat as chat_routes
from src.api.routes import fx as fx_routes
from src.api.routes import ingestion as ingestion_routes
from src.api.routes import manual_je as manual_je_routes
from src.api.routes import master_data as master_data_routes
from src.api.routes import payroll as payroll_routes
from src.api.routes import period as period_routes
from src.api.routes import quarantine as quarantine_routes
from src.api.routes import reports as reports_routes
from src.api.routes import sanctions as sanctions_routes
from src.api.routes import subledgers as subledgers_routes
from src.api.routes import system as system_routes
from src.api.routes import uploads as uploads_routes
from src.core.config import get_settings
from src.core.db import get_engine
from src.core.exceptions import COAValidationError
from src.core.logging import get_logger
from src.ledger.coa import COA, get_active_coa, set_active_coa
from src.ledger.subledger import build_default_registry

logger = get_logger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # Ensure the file-upload directory exists on every startup (dev + prod).
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    try:
        coa = COA.load_from_yaml(settings.coa_path)
        set_active_coa(coa)
        logger.info(
            "coa_loaded",
            path=str(settings.coa_path),
            version=coa.version,
            accounts=len(coa.accounts),
        )
    except (FileNotFoundError, COAValidationError) as exc:
        logger.error("coa_load_failed", error=str(exc))
    yield


app = FastAPI(
    title="Tuitional Finance — CFO API",
    version="0.5.0",
    description="Phase-5 backend: ledger, sub-ledgers, reports, sanctions, period close, FX.",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "cors_allowed_origins", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_routes.router)
app.include_router(uploads_routes.router)
app.include_router(reports_routes.router)
app.include_router(subledgers_routes.router)
app.include_router(manual_je_routes.router)
app.include_router(sanctions_routes.router)
app.include_router(period_routes.router)
app.include_router(fx_routes.router)
app.include_router(chat_routes.router)
app.include_router(ingestion_routes.router)
app.include_router(payroll_routes.router)
app.include_router(quarantine_routes.router)
app.include_router(budget_routes.router)
app.include_router(master_data_routes.router)
app.include_router(system_routes.router)


# ---------------------------------------------------------------------------
# Public / health endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, Any]:
    settings = get_settings()
    try:
        coa = get_active_coa()
        coa_block: dict[str, Any] = {
            "loaded": True,
            "version": coa.version,
            "effective_from": coa.effective_from,
            "accounts": len(coa.accounts),
        }
    except RuntimeError:
        coa_block = {"loaded": False}
    return {
        "service": "tuitional-finance",
        "phase": 5,
        "status": "ok",
        "env": settings.app_env,
        "coa": coa_block,
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(render_prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Liveness probe for k8s / systemd. Doesn't touch the DB."""
    return {"status": "ok"}


@app.get("/db/health")
def db_health() -> dict[str, Any]:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"db unreachable: {type(exc).__name__}: {exc}",
        ) from None
    return {"db": "reachable"}


@app.get("/coa")
def coa_list() -> dict[str, Any]:
    coa = _coa_or_503()
    return {
        "version": coa.version,
        "effective_from": coa.effective_from,
        "accounts": [
            {
                "code": a.code,
                "name": a.name,
                "type": a.type.value,
                "normal_balance": a.normal_balance.value,
                "parent": a.parent,
                "statement": a.statement.value,
                "is_postable": a.is_postable,
                "sub_ledger": a.sub_ledger.value if a.sub_ledger else None,
                "currency": a.currency,
                "is_memo": a.is_memo,
            }
            for a in coa.all_active()
        ],
    }


@app.get("/coa/{code}")
def coa_get(code: str) -> dict[str, Any]:
    coa = _coa_or_503()
    try:
        a = coa.get(code)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"account '{code}' not found") from None
    return {
        "code": a.code,
        "name": a.name,
        "type": a.type.value,
        "normal_balance": a.normal_balance.value,
        "parent": a.parent,
        "statement": a.statement.value,
        "is_postable": a.is_postable,
        "sub_ledger": a.sub_ledger.value if a.sub_ledger else None,
        "currency": a.currency,
        "is_memo": a.is_memo,
        "subtype": a.subtype,
        "description": a.description,
    }


@app.get("/reconcile")
def reconcile_all(
    session: Any = Depends(require_session),
    db: Any = Depends(db_session),
) -> dict[str, Any]:
    registry = build_default_registry()
    out: dict[str, Any] = {}
    for sl in registry.all():
        result = sl.reconcile_to_gl(db)
        out[sl.name.value] = {
            "matches": result.matches,
            "gl_balance": str(result.gl_balance),
            "sub_ledger_sum": str(result.sub_ledger_sum),
            "diff": str(result.diff),
            "control_accounts": list(sl.control_accounts),
        }
    return {"reconciliations": out}


def _coa_or_503() -> COA:
    try:
        return get_active_coa()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
