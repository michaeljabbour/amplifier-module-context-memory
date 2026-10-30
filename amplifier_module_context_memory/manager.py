"""Context-manager adapter: exposes MemoryContextProvider through the Amplifier
``context`` module contract (add_message / get_messages_for_request /
get_messages / set_messages / clear).

Messages are kept in memory (this module does no persistence of its own; the
memory store holds the durable observations).  On the first request of a
session the provider's memory index is retrieved once and injected as a
system-reminder message after any leading system messages.  Retrieval is local
(SQLite/FTS5) and needs no API key.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .provider import MemoryContextProvider

logger = logging.getLogger(__name__)

MEMORY_TAG = "memory-context"


class MemoryContextManager:
    """Minimal ContextManager that prepends retrieved memories to requests."""

    def __init__(
        self,
        provider: Optional[MemoryContextProvider],
        project: Optional[str] = None,
        inject: bool = True,
    ):
        self.provider = provider
        self.project = project
        self.inject = inject
        self._messages: list[dict[str, Any]] = []
        self._memory_message: Optional[dict[str, Any]] = None
        self._memory_loaded = False

    async def add_message(self, message: dict[str, Any]) -> None:
        self._messages.append(message)

    async def get_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    async def set_messages(self, messages: list[dict[str, Any]]) -> None:
        self._messages = list(messages)

    async def clear(self) -> None:
        self._messages = []
        self._memory_message = None
        self._memory_loaded = False

    async def _load_memory(self) -> Optional[dict[str, Any]]:
        if self._memory_loaded:
            return self._memory_message
        self._memory_loaded = True
        if not (self.inject and self.provider):
            return None
        try:
            result = await self.provider.get_context(project=self.project)
        except Exception:
            # Memory is advisory: never break the session, but do not hide it.
            logger.exception("context-memory: retrieval failed; continuing without memories")
            return None
        content = (result or {}).get("content", "")
        if content:
            self._memory_message = {
                "role": "system",
                "content": f"<system-reminder source=\"{MEMORY_TAG}\">\n{content}\n</system-reminder>",
            }
        return self._memory_message

    async def get_messages_for_request(
        self,
        token_budget: int | None = None,
        provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Return a NEW list: history with the memory block after leading system messages."""
        messages = list(self._messages)
        memory = await self._load_memory()
        if memory is None:
            return messages
        idx = 0
        while idx < len(messages) and messages[idx].get("role") == "system":
            idx += 1
        return messages[:idx] + [memory] + messages[idx:]
