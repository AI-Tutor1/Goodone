"""Google Sheets adapter.

Phase 3 ships the interface + a mock; the real implementation needs a
Google service-account JSON path on disk and the spreadsheet IDs in env.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdSpendRow:
    date: str  # YYYY-MM-DD
    channel: str  # google | meta | other
    amount_aed: str  # raw, validated downstream
    campaign_id: str | None = None
    notes: str | None = None


class SheetsAdapter(Protocol):
    def fetch_ad_spend(self) -> Iterable[AdSpendRow]: ...


class MockSheetsAdapter:
    def __init__(self, rows: list[AdSpendRow]) -> None:
        self._rows = rows

    def fetch_ad_spend(self) -> Iterable[AdSpendRow]:
        return list(self._rows)


class GenericSheetsAdapter:
    """Reads any tab from a Google Sheet, returning rows as dicts keyed by header.

    Used by the bulk-upload ingestion endpoint for sessions and enrollments.
    Credentials come from the same service account JSON as ``GoogleSheetsAdapter``.
    """

    def __init__(self, *, sa_json_path: str, spreadsheet_id: str) -> None:
        self._sa_json_path = sa_json_path
        self._spreadsheet_id = spreadsheet_id

    def fetch_rows(self, tab_name: str) -> list[dict[str, str]]:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            self._sa_json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=f"{tab_name}!A:Z")
            .execute()
        )
        rows: list[list[str]] = result.get("values", [])
        if not rows:
            return []
        header = [c.strip().lower() for c in rows[0]]
        return [dict(zip(header, row, strict=False)) for row in rows[1:]]


class GoogleSheetsAdapter:
    """Real Google Sheets adapter.

    Pulls a tab via the Sheets API using the service account at
    ``GOOGLE_SERVICE_ACCOUNT_JSON_PATH``. Imports are lazy so the module
    stays importable when the Google deps aren't installed.
    """

    def __init__(self, *, sa_json_path: str, spreadsheet_id: str, tab_name: str) -> None:
        self._sa_json_path = sa_json_path
        self._spreadsheet_id = spreadsheet_id
        self._tab_name = tab_name

    def fetch_ad_spend(self) -> Iterable[AdSpendRow]:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            self._sa_json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        rng = f"{self._tab_name}!A:Z"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=rng)
            .execute()
        )
        rows: list[list[str]] = result.get("values", [])
        if not rows:
            return
        header = [c.strip().lower() for c in rows[0]]
        for row in rows[1:]:
            r = dict(zip(header, row, strict=False))
            yield AdSpendRow(
                date=str(r.get("date", "")),
                channel=str(r.get("channel", "")).lower(),
                amount_aed=str(r.get("amount_aed", "0")),
                campaign_id=r.get("campaign_id") or None,
                notes=r.get("notes") or None,
            )
