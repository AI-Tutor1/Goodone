"""Pydantic models for the CFO chat module.

Chat is **read-only on the GL** — no tool can mutate ledger state. The
``ToolCall`` / ``ToolResult`` types describe a single GL query the
LLM asked for and the structured answer the chat service returned.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system", "tool"]


class ChatMessage(BaseModel):
    """One message in a chat thread.

    ``role`` follows the OpenAI / Anthropic convention. ``tool_name`` is
    set on ``role == "tool"`` rows so the UI can show "▸ get_account_balance"
    next to the result.
    """

    role: Role
    content: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatTurnRequest(BaseModel):
    """Inbound payload to ``POST /chat/sessions/{id}/messages``."""

    message: str = Field(min_length=1, max_length=4000)


class ChatTurnResponse(BaseModel):
    """One turn — the assistant's answer plus any tool calls it ran."""

    session_id: str
    assistant: ChatMessage
    tool_calls: list[ChatMessage] = Field(default_factory=list)


class ChatSession(BaseModel):
    """In-memory chat session. Production swaps the store implementation
    for a Postgres-backed one; the chat history table is intentionally
    out of the ledger schema (it's not financial data)."""

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[ChatMessage] = Field(default_factory=list)


class ToolDescriptor(BaseModel):
    """How the chat service describes a callable tool to the LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]
