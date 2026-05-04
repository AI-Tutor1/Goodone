"""CFO chat module — read-only LLM access to the GL.

Public exports:

* :class:`ChatService` — turn orchestrator
* :func:`get_chat_provider` / :func:`reset_provider_for_tests` — provider singleton
* :func:`get_default_store` / :func:`reset_default_store` — session store singleton
* :data:`BUILTIN_TOOLS` — tuple of read-only tools wired in by default
* :class:`ChatMessage`, :class:`ChatSession`, :class:`ChatTurnResponse`,
  :class:`ChatTurnRequest` — Pydantic models used at the API boundary
"""

from src.chat.models import (
    ChatMessage,
    ChatSession,
    ChatTurnRequest,
    ChatTurnResponse,
    ToolDescriptor,
)
from src.chat.provider import (
    AnthropicChatProvider,
    ChatProvider,
    ProviderToolCall,
    ProviderTurn,
    StubChatProvider,
    get_chat_provider,
    reset_provider_for_tests,
)
from src.chat.service import (
    MAX_TOOL_ROUNDS,
    ChatService,
    InMemorySessionStore,
    get_default_store,
    reset_default_store,
)
from src.chat.tools import BUILTIN_TOOLS, Tool, builtin_registry

__all__ = [
    "BUILTIN_TOOLS",
    "MAX_TOOL_ROUNDS",
    "AnthropicChatProvider",
    "ChatMessage",
    "ChatProvider",
    "ChatService",
    "ChatSession",
    "ChatTurnRequest",
    "ChatTurnResponse",
    "InMemorySessionStore",
    "ProviderToolCall",
    "ProviderTurn",
    "StubChatProvider",
    "Tool",
    "ToolDescriptor",
    "builtin_registry",
    "get_chat_provider",
    "get_default_store",
    "reset_default_store",
    "reset_provider_for_tests",
]
