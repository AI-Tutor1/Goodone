"""Postgres-backed chat service.

Drop-in replacement for ``ChatService`` that uses ``PostgresChatSessionStore``
instead of ``InMemorySessionStore``. All turn logic is identical — only the
storage calls differ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.chat.models import ChatMessage, ChatSession, ChatTurnResponse
from src.chat.provider import ChatProvider, ProviderTurn
from src.chat.tools import Tool, builtin_registry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.chat.pg_store import PostgresChatSessionStore

MAX_TOOL_ROUNDS = 3


class PgChatService:
    def __init__(
        self,
        *,
        provider: ChatProvider,
        pg_store: "PostgresChatSessionStore",
        tools: dict[str, Tool] | None = None,
    ) -> None:
        self._provider = provider
        self._store = pg_store
        self._tools = tools if tools is not None else builtin_registry()

    @property
    def tool_descriptors(self) -> list[Any]:
        return [t.descriptor() for t in self._tools.values()]

    def create_session(self, *, user_id: str, db: "Session") -> ChatSession:
        return self._store.create(user_id=user_id, db=db)

    def turn(self, *, session_id: str, user_message: str, db: "Session") -> ChatTurnResponse:
        sess = self._store.get(session_id, db=db)
        if sess is None:
            raise KeyError(f"unknown chat session: {session_id}")

        user_msg = ChatMessage(role="user", content=user_message)
        self._store.append(session_id, user_msg, db=db)

        tool_messages: list[ChatMessage] = []
        for _round in range(MAX_TOOL_ROUNDS):
            sess = self._store.get(session_id, db=db)
            assert sess is not None
            intent = self._provider.turn(history=sess.messages, tools=self.tool_descriptors)
            if not intent.tool_calls:
                return self._finalise(session_id, intent, tool_messages, db=db)
            tool_results = self._run_tool_calls(intent, db, tool_messages, session_id)
            sess = self._store.get(session_id, db=db)
            assert sess is not None
            intent = self._provider.continue_with_tool_results(
                history=sess.messages,
                tools=self.tool_descriptors,
                tool_results=tool_results,
            )
            if not intent.tool_calls:
                return self._finalise(session_id, intent, tool_messages, db=db)

        fallback = ProviderTurn(
            text="(stopped after too many tool rounds — narrow your question and try again)"
        )
        return self._finalise(session_id, fallback, tool_messages, db=db)

    def _run_tool_calls(
        self,
        intent: ProviderTurn,
        db: "Session",
        sink: list[ChatMessage],
        session_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []
        for call in intent.tool_calls:
            tool = self._tools.get(call.name)
            if tool is None:
                payload: dict[str, Any] = {"error": f"unknown tool: {call.name}"}
            else:
                try:
                    payload = tool.fn(db, call.input)
                except Exception as exc:
                    payload = {"error": f"{type(exc).__name__}: {exc}"}
            results.append((call.name, payload))
            tool_msg = ChatMessage(
                role="tool",
                content=str(payload),
                tool_name=call.name,
                tool_input=call.input,
            )
            self._store.append(session_id, tool_msg, db=db)
            sink.append(tool_msg)
        return results

    def _finalise(
        self,
        session_id: str,
        intent: ProviderTurn,
        tool_messages: list[ChatMessage],
        *,
        db: "Session",
    ) -> ChatTurnResponse:
        assistant = ChatMessage(role="assistant", content=intent.text or "(no answer)")
        self._store.append(session_id, assistant, db=db)
        return ChatTurnResponse(
            session_id=session_id,
            assistant=assistant,
            tool_calls=list(tool_messages),
        )
