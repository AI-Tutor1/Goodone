"""Unit tests for the validation rule engine."""

from __future__ import annotations

from src.validation.rules import (
    bank_transaction_ruleset,
    is_one_of,
    lms_session_ruleset,
    numeric_range,
    regex,
    required,
)


def test_required_rejects_missing() -> None:
    rule = required("foo")
    assert rule({}).ok is False
    assert rule({"foo": ""}).ok is False
    assert rule({"foo": "x"}).ok is True


def test_is_one_of() -> None:
    rule = is_one_of("status", {"ok", "fail"})
    assert rule({"status": "ok"}).ok is True
    assert rule({"status": "weird"}).ok is False


def test_numeric_range() -> None:
    rule = numeric_range("n", lo=0, hi=10)
    assert rule({"n": 5}).ok is True
    assert rule({"n": "5"}).ok is True
    assert rule({"n": 11}).ok is False
    assert rule({"n": "abc"}).ok is False


def test_regex() -> None:
    rule = regex("date", r"\d{4}-\d{2}-\d{2}")
    assert rule({"date": "2026-04-15"}).ok is True
    assert rule({"date": "15/04/2026"}).ok is False
    assert rule({"date": None}).ok is False


def test_lms_ruleset_happy() -> None:
    payload = {
        "session_id": "S1",
        "enrollment_id": 42,
        "scheduled_minutes": 60,
        "conducted_minutes": 58,
        "status": "conducted",
    }
    failures = lms_session_ruleset().evaluate(payload)
    assert failures == []


def test_lms_ruleset_finds_all_failures() -> None:
    payload = {"session_id": "", "status": "weird"}
    failures = lms_session_ruleset().evaluate(payload)
    codes = {f.code for f in failures}
    assert "REQUIRED" in codes
    assert "NOT_IN_ENUM" in codes
    # The rule engine returns ALL failures (not first-fail).
    assert len(failures) >= 3


def test_bank_ruleset() -> None:
    failures = bank_transaction_ruleset().evaluate(
        {"date": "2026-04-15", "amount_aed": "100", "description": "Topup"},
    )
    assert failures == []
