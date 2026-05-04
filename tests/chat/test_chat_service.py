"""Unit tests for the chat service.

We exercise the orchestration logic with the deterministic ``StubChatProvider``
and a fake DB session — no Postgres required, so these run in the unit-test
job. Integration tests against a real GL go in ``tests/db/`` (out of scope
for this file).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.chat import (
    ChatService,
    InMemorySessionStore,
    ProviderToolCall,
    ProviderTurn,
    StubChatProvider,
    Tool,
    builtin_registry,
)


class _FakeDB:
    """Stand-in for a SQLAlchemy session — never queried because we
    swap in fake tools that don't touch the DB."""


def _fake_tools() -> dict[str, Tool]:
    """Lightweight tool set that mirrors the real names + schemas but
    returns canned dicts. Lets us assert orchestration without spinning up
    Postgres."""
    real = builtin_registry()
    return {
        name: Tool(
            name=name,
            description=t.description,
            input_schema=t.input_schema,
            fn=lambda _db, args, _n=name: {"echo_tool": _n, "echo_args": args, "ok": True},
        )
        for name, t in real.items()
    }


@pytest.fixture
def service() -> ChatService:
    return ChatService(
        provider=StubChatProvider(),
        store=InMemorySessionStore(),
        tools=_fake_tools(),
    )


def test_create_session_returns_unique_ids(service: ChatService) -> None:
    a = service.create_session()
    b = service.create_session()
    assert a.id != b.id
    assert len(a.id) == 12


def test_capabilities_response_when_no_keyword_match(service: ChatService) -> None:
    sess = service.create_session()
    resp = service.turn(session_id=sess.id, user_message="hello there", db=_FakeDB())
    assert resp.tool_calls == []
    assert "Available tools" in resp.assistant.content


def test_balance_question_invokes_account_tool(service: ChatService) -> None:
    sess = service.create_session()
    resp = service.turn(
        session_id=sess.id,
        user_message="What is the balance of account 2050?",
        db=_FakeDB(),
    )
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.tool_name == "get_account_balance"
    assert tc.tool_input == {"account_code": "2050"}
    # The stub provider quotes the tool result in its answer.
    assert "get_account_balance" in resp.assistant.content


def test_pnl_question_extracts_period(service: ChatService) -> None:
    sess = service.create_session()
    resp = service.turn(
        session_id=sess.id,
        user_message="show me P&L for 2026-04",
        db=_FakeDB(),
    )
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.tool_name == "get_pnl"
    assert tc.tool_input == {"period": "2026-04"}


def test_unknown_session_raises(service: ChatService) -> None:
    with pytest.raises(KeyError):
        service.turn(session_id="nope", user_message="hi", db=_FakeDB())


def test_history_persisted_across_turns(service: ChatService) -> None:
    sess = service.create_session()
    service.turn(session_id=sess.id, user_message="hi", db=_FakeDB())
    service.turn(session_id=sess.id, user_message="balance of 1000?", db=_FakeDB())
    persisted = service._store.get(sess.id)
    assert persisted is not None
    # user, assistant (capabilities), user, tool, assistant
    roles = [m.role for m in persisted.messages]
    assert roles[:2] == ["user", "assistant"]
    assert "tool" in roles[2:]


def test_unknown_tool_call_returns_error_payload() -> None:
    """Provider asks for a tool that isn't in the registry → service
    surfaces the error in a tool message instead of crashing."""

    class _GhostProvider:
        def turn(self, *, history: list, tools: list) -> ProviderTurn:
            return ProviderTurn(tool_calls=[ProviderToolCall(name="ghost", input={})])

        def continue_with_tool_results(
            self,
            *,
            history: list,
            tools: list,
            tool_results: list[tuple[str, dict[str, Any]]],
        ) -> ProviderTurn:
            return ProviderTurn(text=f"saw: {tool_results[-1][1]}")

    svc = ChatService(provider=_GhostProvider(), store=InMemorySessionStore(), tools=_fake_tools())
    sess = svc.create_session()
    resp = svc.turn(session_id=sess.id, user_message="anything", db=_FakeDB())
    assert "unknown tool" in resp.tool_calls[0].content


def test_descriptors_match_registry(service: ChatService) -> None:
    descriptors = service.tool_descriptors
    names = {d.name for d in descriptors}
    expected = set(builtin_registry().keys())
    assert names == expected
