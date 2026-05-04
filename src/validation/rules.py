"""Validation rule engine.

Per ``docs/rules/ingestion_rules.md``: every ingested row passes through a
chain of pure functions. A failed rule sends the raw payload to
``staging.data_quality_quarantine`` rather than dropping it.

Rules are plain callables with the signature
``(payload: dict) -> RuleResult``. Compose them with :class:`RuleSet`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    code: str = ""
    message: str = ""
    field: str | None = None


Rule = Callable[[dict], RuleResult]


@dataclass
class RuleSet:
    """Chain of rules applied to one payload."""

    name: str
    rules: list[Rule] = field(default_factory=list)

    def add(self, rule: Rule) -> RuleSet:
        self.rules.append(rule)
        return self

    def evaluate(self, payload: dict) -> list[RuleResult]:
        """Return every failure (empty list on success). All rules run."""
        return [r for r in (rule(payload) for rule in self.rules) if not r.ok]


# ---------------------------------------------------------------------------
# Common rules
# ---------------------------------------------------------------------------


def required(field_name: str) -> Rule:
    def _rule(p: dict) -> RuleResult:
        if field_name not in p or p[field_name] in (None, ""):
            return RuleResult(
                False,
                code="REQUIRED",
                message=f"missing required field '{field_name}'",
                field=field_name,
            )
        return RuleResult(True)

    return _rule


def is_one_of(field_name: str, allowed: set[str]) -> Rule:
    def _rule(p: dict) -> RuleResult:
        v = p.get(field_name)
        if v not in allowed:
            return RuleResult(
                False,
                code="NOT_IN_ENUM",
                message=f"{field_name}={v!r} not in {sorted(allowed)}",
                field=field_name,
            )
        return RuleResult(True)

    return _rule


def numeric_range(field_name: str, *, lo: float, hi: float) -> Rule:
    def _rule(p: dict) -> RuleResult:
        v = p.get(field_name)
        try:
            n = float(v)  # validation only: caller still uses Decimal in calc core
        except (TypeError, ValueError):
            return RuleResult(
                False,
                code="NOT_NUMERIC",
                message=f"{field_name}={v!r} not numeric",
                field=field_name,
            )
        if not (lo <= n <= hi):
            return RuleResult(
                False,
                code="OUT_OF_RANGE",
                message=f"{field_name}={n} outside [{lo},{hi}]",
                field=field_name,
            )
        return RuleResult(True)

    return _rule


def regex(field_name: str, pattern: str) -> Rule:
    import re as _re

    rx = _re.compile(pattern)

    def _rule(p: dict) -> RuleResult:
        v = p.get(field_name)
        if not isinstance(v, str) or not rx.fullmatch(v):
            return RuleResult(
                False,
                code="REGEX_MISMATCH",
                message=f"{field_name}={v!r} doesn't match {pattern}",
                field=field_name,
            )
        return RuleResult(True)

    return _rule


# ---------------------------------------------------------------------------
# Pre-built rule sets
# ---------------------------------------------------------------------------


def lms_session_ruleset() -> RuleSet:
    """Validate one session payload from the LMS adapter."""
    rs = RuleSet("lms_session")
    rs.add(required("session_id"))
    rs.add(required("enrollment_id"))
    rs.add(required("status"))
    rs.add(
        is_one_of(
            "status",
            {
                "conducted",
                "student_absent",
                "teacher_absent",
                "cancelled",
                "no_show",
            },
        )
    )
    rs.add(numeric_range("scheduled_minutes", lo=15, hi=180))
    rs.add(numeric_range("conducted_minutes", lo=0, hi=180))
    return rs


def bank_transaction_ruleset() -> RuleSet:
    rs = RuleSet("bank_transaction")
    rs.add(required("date"))
    rs.add(required("amount_aed"))
    rs.add(required("description"))
    rs.add(regex("date", r"\d{4}-\d{2}-\d{2}"))
    return rs
