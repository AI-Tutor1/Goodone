"""Manual upload helper.

Used for Month-1 backfills (payroll screenshots, opening balances) where
no API is yet wired. Files land on disk; this module records metadata in
``staging.manual_uploads``-style table (Phase 3 stub — table TBD if we
need it; for now we just mint a deterministic batch_id and stream rows
straight into the validation pipeline).
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable
from io import StringIO


def batch_id(content: str, *, source: str) -> str:
    h = hashlib.sha256()
    h.update(source.encode("utf-8"))
    h.update(b"\n")
    h.update(content.encode("utf-8"))
    return f"{source}:{h.hexdigest()[:12]}"


def parse_csv(content: str) -> Iterable[dict[str, str]]:
    """Generic CSV → dict iterator. Validation is the caller's job."""
    yield from csv.DictReader(StringIO(content))
