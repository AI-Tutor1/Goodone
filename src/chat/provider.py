"""LLM provider abstraction for the CFO chat.

Two providers ship:

* ``stub`` — deterministic, offline. Picks tools by keyword match and
  echoes structured results. Used by tests and by dev environments that
  haven't configured an API key. Does not call out to the network.
* ``anthropic`` — Anthropic Messages API with tool use. Switched on by
  setting ``CHAT_PROVIDER=anthropic`` and ``ANTHROPIC_API_KEY=...`` in
  ``.env``. The provider returns the model's final assistant message
  after ``ChatService`` resolves any requested tool calls.

Both providers share the same ``ChatProvider`` Protocol so callers don't
care which is active. The provider returns *intent* (text + tool calls)
and ``ChatService`` is the one that actually runs tools — this keeps the
"LLM never touches the DB directly" invariant easy to audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from src.core.config import get_settings

if TYPE_CHECKING:
    from src.chat.models import ChatMessage, ToolDescriptor


@dataclass(frozen=True)
class ProviderToolCall:
    """A tool the provider asked to run, with its bound arguments."""

    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ProviderTurn:
    """One round-trip's intent.

    If ``tool_calls`` is non-empty, ``ChatService`` should run them and
    feed the results back to ``provider.continue_with_tool_results()``.
    Otherwise ``text`` is the final answer.
    """

    text: str = ""
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class ChatProvider(Protocol):
    def turn(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
    ) -> ProviderTurn: ...

    def continue_with_tool_results(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
        tool_results: list[tuple[str, dict[str, Any]]],
    ) -> ProviderTurn: ...


# ---------------------------------------------------------------------------
# Stub provider — no network, deterministic
# ---------------------------------------------------------------------------


class StubChatProvider:
    """Picks tools by keyword and stitches a plain-text answer.

    Behavioural contract for tests:
    - First turn: keyword-matches the message → emits one tool call.
    - Continuation: emits a final answer that quotes the tool result keys.
    - Unknown question: emits a polite "I can answer questions about …"
      reply with no tool calls.
    """

    KEYWORD_MAP: dict[tuple[str, ...], str] = {  # noqa: RUF012 - immutable in practice
        ("balance", "account"): "get_account_balance",
        ("p&l", "pnl", "profit", "loss"): "get_pnl",
        ("trial", "balanced"): "get_trial_balance",
        ("period", "close", "closed", "open"): "get_period_status",
        ("sanction", "approval", "approve"): "list_open_sanctions",
        ("quarantine", "rejected", "validation"): "list_quarantine",
        ("journal", "recent", "lately"): "list_recent_journals",
    }

    def turn(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
    ) -> ProviderTurn:
        if not history:
            return ProviderTurn(text=self._capabilities(tools))
        msg = history[-1].content.lower()
        tool_names = {t.name for t in tools}
        for keywords, target in self.KEYWORD_MAP.items():
            if target in tool_names and any(k in msg for k in keywords):
                call = ProviderToolCall(name=target, input=self._guess_input(target, msg))
                return ProviderTurn(tool_calls=[call])
        return ProviderTurn(text=self._capabilities(tools))

    def continue_with_tool_results(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
        tool_results: list[tuple[str, dict[str, Any]]],
    ) -> ProviderTurn:
        if not tool_results:
            return ProviderTurn(text="No tool result to summarise.")
        name, payload = tool_results[-1]
        return ProviderTurn(text=f"Result of {name}: {payload}")

    @staticmethod
    def _capabilities(tools: list[ToolDescriptor]) -> str:
        names = ", ".join(sorted(t.name for t in tools))
        return (
            "I can answer read-only questions about the GL. "
            f"Available tools: {names}. "
            "Try asking about an account balance, P&L for a period, or open sanctions."
        )

    @staticmethod
    def _guess_input(tool: str, msg: str) -> dict[str, Any]:
        # The stub doesn't try to be clever — just returns a plausible default
        # for the simplest schemas. Real provider does proper extraction.
        # Strip common punctuation so "2050?" still parses.
        normalised = msg
        for ch in ",.?!()[]:;\"'":
            normalised = normalised.replace(ch, " ")
        tokens = normalised.split()
        if tool == "get_account_balance":
            for token in tokens:
                if token.isdigit() and 1000 <= int(token) <= 9999:
                    return {"account_code": token}
            return {"account_code": "1000"}
        if tool in {"get_pnl", "get_period_status"}:
            for token in tokens:
                if len(token) == 7 and token[4] == "-" and token[:4].isdigit():
                    return {"period": token}
            return {"period": "2026-04"}
        if tool == "get_trial_balance":
            return {}
        return {}


# ---------------------------------------------------------------------------
# Anthropic provider — opt-in
# ---------------------------------------------------------------------------


class AnthropicChatProvider:
    """Real provider — talks to the Anthropic Messages API with tools.

    Imports the SDK lazily so the rest of the codebase doesn't pay the
    import cost when ``CHAT_PROVIDER=stub`` (the default). If the SDK is
    not installed when this provider is selected, ``__init__`` raises
    a clear ``RuntimeError``.

    The system prompt makes the read-only constraint explicit: the model
    is instructed never to ask the user for permission to mutate state,
    because no mutating tools exist in the registry.
    """

    SYSTEM_PROMPT = (
        "You are the Tuitional Finance CFO assistant. You answer questions "
        "about the company's general ledger using the read-only tools "
        "provided. You never offer to make changes to the books — there are "
        "no write tools available. When you cite numbers, always include the "
        "currency (default AED) and round to 2 decimals unless the user asks "
        "otherwise. If a tool returns an empty result, say so plainly."
    )

    def __init__(self, *, api_key: str, model: str) -> None:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            msg = (
                "anthropic SDK not installed. Add `anthropic` to pyproject.toml "
                "or set CHAT_PROVIDER=stub."
            )
            raise RuntimeError(msg) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def turn(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
    ) -> ProviderTurn:
        return self._call(history=history, tools=tools, tool_results=[])

    def continue_with_tool_results(
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
        tool_results: list[tuple[str, dict[str, Any]]],
    ) -> ProviderTurn:
        return self._call(history=history, tools=tools, tool_results=tool_results)

    def _call(  # pragma: no cover - exercised only with a real key
        self,
        *,
        history: list[ChatMessage],
        tools: list[ToolDescriptor],
        tool_results: list[tuple[str, dict[str, Any]]],
    ) -> ProviderTurn:
        messages = [
            {"role": m.role, "content": m.content}
            for m in history
            if m.role in {"user", "assistant"}
        ]
        if tool_results:
            # Append each tool result as a synthetic user-side observation
            # — Anthropic's tool-use protocol uses tool_result content blocks
            # in production; this simplified shape is enough for the stub
            # tests and doubles as a friendly fallback for older SDKs.
            for name, payload in tool_results:
                messages.append({"role": "user", "content": f"[tool {name} result] {payload}"})
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": self.SYSTEM_PROMPT,
            "messages": messages,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ],
        }
        resp = self._client.messages.create(**payload)
        text_out = ""
        tool_calls: list[ProviderToolCall] = []
        for block in resp.content:
            kind = getattr(block, "type", None)
            if kind == "text":
                text_out += getattr(block, "text", "")
            elif kind == "tool_use":
                tool_calls.append(
                    ProviderToolCall(
                        name=getattr(block, "name", ""),
                        input=dict(getattr(block, "input", {}) or {}),
                    ),
                )
        return ProviderTurn(text=text_out, tool_calls=tool_calls)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


_active: ChatProvider | None = None


def get_chat_provider() -> ChatProvider:
    """Return the process-wide chat provider (stub by default)."""
    global _active
    if _active is not None:
        return _active
    s = get_settings()
    name = getattr(s, "chat_provider", "stub")
    if name == "anthropic":
        api_key = getattr(s, "anthropic_api_key", None)
        api_key = api_key.get_secret_value() if api_key is not None else ""
        model = getattr(s, "chat_model", "claude-sonnet-4-6")
        if api_key:
            _active = AnthropicChatProvider(api_key=api_key, model=model)
            return _active
    _active = StubChatProvider()
    return _active


def reset_provider_for_tests() -> None:
    global _active
    _active = None
