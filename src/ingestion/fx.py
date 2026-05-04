"""FX rate ingestion.

Daily pull from exchangerate.host. The puller is idempotent (the
``master.fx_rates`` UNIQUE constraint on ``(date, base, quote, source)``
handles re-runs cleanly). A manual override path lets the CFO replace a
specific date's rate at month end — those rows carry ``source='manual'``
and take precedence in the FX agent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import text

from src.core.money import fx_rate as _q

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class FxQuote:
    date: date
    base: str
    quote: str
    rate: Decimal
    source: str  # "exchangerate.host" | "manual"


# ---------------------------------------------------------------------------


def fetch_quotes(
    *,
    base: str,
    quotes: list[str],
    start: date,
    end: date,
    api_base: str = "https://api.exchangerate.host",
) -> Iterable[FxQuote]:
    """Yield daily quotes from exchangerate.host's ``/timeseries``.

    The API returns ``{"rates": {"YYYY-MM-DD": {"PKR": 75.50, ...}, ...}}``.
    """
    params = {
        "base": base,
        "symbols": ",".join(quotes),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(f"{api_base}/timeseries", params=params)
        resp.raise_for_status()
        payload = resp.json()
    rates_by_day: dict[str, dict[str, float]] = payload.get("rates", {})
    for day_str, by_quote in sorted(rates_by_day.items()):
        d = date.fromisoformat(day_str)
        for q, raw in by_quote.items():
            yield FxQuote(
                date=d,
                base=base,
                quote=q,
                rate=_q(str(raw)),
                source="exchangerate.host",
            )


def upsert(session: Session, quotes: Iterable[FxQuote]) -> int:
    """Insert quotes; returns count written. Duplicates are ignored."""
    n = 0
    for q in quotes:
        session.execute(
            text(
                """
                INSERT INTO master.fx_rates (date, base, quote, rate, source)
                VALUES (:d, :b, :q, :r, :s)
                ON CONFLICT (date, base, quote, source) DO NOTHING
                """,
            ),
            {"d": q.date, "b": q.base, "q": q.quote, "r": q.rate, "s": q.source},
        )
        n += 1
    return n


def manual_override(
    session: Session,
    *,
    day: date,
    base: str,
    quote: str,
    rate: Decimal,
    by: str,
) -> None:
    """CFO override at month end. Wins over the daily auto-pull."""
    session.execute(
        text(
            """
            INSERT INTO master.fx_rates (date, base, quote, rate, source)
            VALUES (:d, :b, :q, :r, :s)
            ON CONFLICT (date, base, quote, source) DO UPDATE SET rate = EXCLUDED.rate
            """,
        ),
        {"d": day, "b": base, "q": quote, "r": _q(rate), "s": "manual"},
    )
    # audit row
    session.execute(
        text(
            "INSERT INTO audit.audit_log (ts, actor, action, target_type, "
            "                              target_id, success) "
            "VALUES (NOW(), :by, 'COA_LOAD', 'fx_rate', :tid, true)",
        ),
        {"by": by, "tid": f"{day} {base}->{quote}"},
    )


def effective_rate(
    session: Session,
    *,
    day: date,
    base: str,
    quote: str,
) -> Decimal | None:
    """Return the effective rate for *day*, preferring ``manual`` over auto-pull."""
    row = session.execute(
        text(
            "SELECT rate, source FROM master.fx_rates "
            "WHERE date = :d AND base = :b AND quote = :q "
            "ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END LIMIT 1",
        ),
        {"d": day, "b": base, "q": quote},
    ).one_or_none()
    return _q(row.rate) if row else None
