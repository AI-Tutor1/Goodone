"""Unit tests for the LMS mock adapter."""

from __future__ import annotations

from src.ingestion.lms import MockLmsAdapter, SessionPayload


def _payload(session_id: str, occurred_on: str, status: str = "conducted") -> SessionPayload:
    return SessionPayload(
        session_id=session_id,
        enrollment_id=1,
        scheduled_minutes=60,
        conducted_minutes=58,
        status=status,
        occurred_on=occurred_on,
    )


def test_mock_returns_only_after_since() -> None:
    rows = [
        _payload("S1", "2026-04-01"),
        _payload("S2", "2026-04-15"),
        _payload("S3", "2026-04-30"),
    ]
    adapter = MockLmsAdapter(rows)
    assert [s.session_id for s in adapter.fetch_sessions("2026-04-15")] == ["S2", "S3"]
    assert [s.session_id for s in adapter.fetch_sessions("2026-05-01")] == []
