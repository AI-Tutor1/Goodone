"""StubChatProvider — keyword-routing + input extraction."""

from __future__ import annotations

from src.chat.models import ChatMessage, ToolDescriptor
from src.chat.provider import StubChatProvider


def _descriptors() -> list[ToolDescriptor]:
    # A subset is enough — the provider only filters by name presence.
    return [
        ToolDescriptor(
            name=n,
            description="",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        for n in (
            "get_account_balance",
            "get_pnl",
            "get_trial_balance",
            "get_period_status",
            "list_open_sanctions",
            "list_quarantine",
            "list_recent_journals",
        )
    ]


def _user(text: str) -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def test_empty_history_returns_capabilities() -> None:
    intent = StubChatProvider().turn(history=[], tools=_descriptors())
    assert intent.tool_calls == []
    assert "Available tools" in intent.text


def test_balance_keyword_picks_account_tool() -> None:
    intent = StubChatProvider().turn(
        history=_user("What's the balance of account 2050?"),
        tools=_descriptors(),
    )
    assert len(intent.tool_calls) == 1
    assert intent.tool_calls[0].name == "get_account_balance"
    assert intent.tool_calls[0].input == {"account_code": "2050"}


def test_balance_without_code_falls_back_to_default() -> None:
    intent = StubChatProvider().turn(
        history=_user("show me an account balance"),
        tools=_descriptors(),
    )
    assert intent.tool_calls[0].input == {"account_code": "1000"}


def test_pnl_keyword_picks_pnl_tool() -> None:
    intent = StubChatProvider().turn(
        history=_user("profit for 2026-04 please"),
        tools=_descriptors(),
    )
    assert intent.tool_calls[0].name == "get_pnl"
    assert intent.tool_calls[0].input == {"period": "2026-04"}


def test_period_keyword_picks_period_status_tool() -> None:
    intent = StubChatProvider().turn(
        history=_user("is period 2026-03 closed?"),
        tools=_descriptors(),
    )
    assert intent.tool_calls[0].name == "get_period_status"
    assert intent.tool_calls[0].input == {"period": "2026-03"}


def test_sanction_keyword_picks_sanctions_tool() -> None:
    intent = StubChatProvider().turn(
        history=_user("any sanction approvals waiting?"),
        tools=_descriptors(),
    )
    assert intent.tool_calls[0].name == "list_open_sanctions"


def test_continue_summarises_tool_result() -> None:
    intent = StubChatProvider().continue_with_tool_results(
        history=_user("hi"),
        tools=_descriptors(),
        tool_results=[("get_pnl", {"net_profit": "12345.67"})],
    )
    assert "get_pnl" in intent.text
    assert "12345.67" in intent.text
