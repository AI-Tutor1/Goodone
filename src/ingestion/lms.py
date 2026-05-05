"""LMS adapter.

Two implementations:

* :class:`LmsHttpAdapter` — pulls from a real LMS over HTTPS. Wired up but
  never tested with prod creds in this codebase; switch on by setting
  ``LMS_API_BASE_URL`` + ``LMS_API_KEY``.
* :class:`MockLmsAdapter` — returns a fixture payload. Used by tests.

Both implement the same :class:`LmsAdapter` Protocol so callers can swap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class SessionPayload:
    session_id: str
    enrollment_id: int
    scheduled_minutes: int
    conducted_minutes: int
    status: str  # one of conducted / student_absent / teacher_absent / cancelled / no_show
    occurred_on: str  # YYYY-MM-DD


class LmsAdapter(Protocol):
    def fetch_sessions(self, since: str) -> Iterable[SessionPayload]:
        """Return every session record with occurred_on >= ``since``."""


# ---------------------------------------------------------------------------


class LmsHttpAdapter:
    """Real LMS adapter. Phase 3 ships the call shape; a vendor sample is
    needed to lock the JSON shape, then this passes integration tests."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def fetch_sessions(self, since: str) -> Iterable[SessionPayload]:
        url = f"{self._base_url}/sessions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        params = {"since": since}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            for row in resp.json().get("sessions", []):
                yield SessionPayload(
                    session_id=str(row["id"]),
                    enrollment_id=int(row["enrollment_id"]),
                    scheduled_minutes=int(row["scheduled_minutes"]),
                    conducted_minutes=int(row["conducted_minutes"]),
                    status=str(row["status"]),
                    occurred_on=str(row["occurred_on"]),
                )


# ---------------------------------------------------------------------------


class MockLmsAdapter:
    """Returns whatever you give it. Used by tests + dev seed."""

    def __init__(self, sessions: list[SessionPayload]) -> None:
        self._sessions = sessions

    def fetch_sessions(self, since: str) -> Iterable[SessionPayload]:
        return [s for s in self._sessions if s.occurred_on >= since]


# ---------------------------------------------------------------------------
# CSV / XLSX row parser — used by the bulk-upload ingestion endpoint.
# ---------------------------------------------------------------------------

REQUIRED_SESSION_COLUMNS = {
    "session_id",
    "enrollment_id",
    "scheduled_minutes",
    "conducted_minutes",
    "status",
    "occurred_on",
}

VALID_STATUSES = {"conducted", "student_absent", "teacher_absent", "cancelled", "no_show"}


def parse_session_row(row: dict[str, str]) -> SessionPayload:
    """Parse one dict row (from CSV DictReader or XLSX) into a SessionPayload.

    Raises ``ValueError`` with a human-readable message on bad data so the
    caller can quarantine the row without crashing the batch.
    """
    missing = REQUIRED_SESSION_COLUMNS - set(row.keys())
    if missing:
        raise ValueError(f"missing columns: {', '.join(sorted(missing))}")

    status = str(row["status"]).strip().lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status '{status}'; must be one of {sorted(VALID_STATUSES)}")

    try:
        scheduled = int(row["scheduled_minutes"])
        conducted = int(row["conducted_minutes"])
    except ValueError as exc:
        raise ValueError(f"non-integer minutes: {exc}") from exc

    if scheduled <= 0:
        raise ValueError(f"scheduled_minutes must be > 0, got {scheduled}")
    if conducted < 0:
        raise ValueError(f"conducted_minutes must be >= 0, got {conducted}")

    try:
        enrollment_id = int(row["enrollment_id"])
    except ValueError as exc:
        raise ValueError(f"enrollment_id must be integer: {exc}") from exc

    occurred_on = str(row["occurred_on"]).strip()
    # Normalise YYYY-MM-DD; reject anything else.
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])-([0-2]\d|3[01])$", occurred_on):
        raise ValueError(f"occurred_on must be YYYY-MM-DD, got '{occurred_on}'")

    return SessionPayload(
        session_id=str(row["session_id"]).strip(),
        enrollment_id=enrollment_id,
        scheduled_minutes=scheduled,
        conducted_minutes=conducted,
        status=status,
        occurred_on=occurred_on,
    )
