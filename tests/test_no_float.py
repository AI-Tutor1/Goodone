"""Static guard: ``float`` must not appear in the calc core.

Scans ``src/ledger/`` and ``src/subledgers/`` for the substrings ``float(`` and
``: float`` and ``-> float``. Any hit is a regression — fix or move the helper
to ``src/core/``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "src" / "ledger", ROOT / "src" / "subledgers"]
PATTERNS = [
    re.compile(r"\bfloat\("),
    re.compile(r":\s*float\b"),
    re.compile(r"->\s*float\b"),
]


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        files.extend(root.rglob("*.py"))
    return files


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_float_in_calc_core(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # ignore comments and docstrings cheaply
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pat in PATTERNS:
            if pat.search(line):
                hits.append((lineno, line.rstrip()))
                break
    assert not hits, f"{path.relative_to(ROOT)} contains forbidden 'float' usage:\n" + "\n".join(
        f"  {ln}: {src}" for ln, src in hits
    )


def test_scan_finds_at_least_one_file() -> None:
    """Sanity check: don't silently green if the scan dirs vanish."""
    assert _python_files(), (
        f"no Python files found under {SCAN_DIRS}; static-scan guard would be a no-op"
    )
