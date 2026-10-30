"""Read adapter for tool-memory's native client; no daemon/credential discovery."""

from __future__ import annotations

import asyncio
from typing import Any


class NativeMemoryContextProvider:
    """Expose an explicitly scoped native index without inventing legacy records.

    The injected client owns its transport. This adapter invokes only ``index``
    and ``search``. It never writes, creates a client or starts a daemon itself.
    Native index entries are room abstracts/overviews, not observation records
    or session summaries. Scope is supplied by the host and is not auth policy.
    """

    name = "memory_context"

    @staticmethod
    def validate_config(config: dict[str, Any]) -> None:
        wing = config.get("native_wing")
        room = config.get("native_room")
        if not isinstance(wing, str) or not wing.strip():
            raise ValueError("Native memory requires a nonempty native_wing")
        if room is not None and (not isinstance(room, str) or not room.strip()):
            raise ValueError("native_room must be a nonempty string when supplied")
        for key, default in (("index_limit", 50), ("token_budget", 2000)):
            value = config.get(key, default)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} must be a positive integer")

    def __init__(self, client: Any, config: dict[str, Any]):
        self.validate_config(config)
        if not all(callable(getattr(client, name, None)) for name in ("index", "search")):
            raise ValueError("Native client must implement index and search")
        self.client = client
        self.wing = config["native_wing"]
        self.room = config.get("native_room")
        self.index_limit = config.get("index_limit", 50)
        self.token_budget = config.get("token_budget", 2000)

    async def get_context(self, project=None, include_summary=True, include_index=True, **kwargs):
        if project is not None:
            raise ValueError("Native memory uses configured wing/room, not legacy project filters")
        metadata = {"provider": self.name, "backend": "native", "wing": self.wing,
                    "room": self.room, "session_summaries": "unsupported",
                    "lookback_filter": "not applied to native room index"}
        if not include_index:
            return {"content": "", "metadata": metadata}
        entries = await asyncio.to_thread(self.client.index, wing=self.wing, room=self.room)
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError("Invalid native index response")
        parts = []
        # Same approximate character/token conversion as a small display budget,
        # never a claim of tokenizer-exact accounting.
        budget = self.token_budget * 4
        for entry in entries[:self.index_limit]:
            if not all(isinstance(entry.get(key, ""), str) for key in ("scope", "abstract", "overview")):
                raise ValueError("Invalid native index text")
            section = "\n".join([entry.get("scope", ""), entry.get("abstract", ""), entry.get("overview", "")]).strip()
            if not section:
                continue
            if budget <= 0:
                break
            snippet = section[:budget]
            parts.append(snippet)
            budget -= len(snippet) + 2
        metadata.update(index_entry_count=len(parts), total_index_entries=len(entries))
        content = "## Native Memory Index\n" + "\n\n".join(parts) if parts else ""
        return {"content": content, "metadata": metadata}

    async def get_relevant_memories(self, query: str, limit: int = 10, project=None):
        if project is not None:
            raise ValueError("Native memory uses configured wing/room, not legacy project filters")
        if not isinstance(query, str) or type(limit) is not int or limit <= 0:
            raise ValueError("Native search requires text and a positive limit")
        result = await asyncio.to_thread(self.client.search, query, k=limit, wing=self.wing, room=self.room)
        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise ValueError("Invalid native search response")
        # Preserve degradation metadata instead of discarding it as an empty list.
        return result

    async def get_memory_by_id(self, memory_id: str):
        raise NotImplementedError("Native reads use scoped search refs; legacy observation-ID lookup is unsupported")

    async def get_file_context(self, file_path: str, limit: int = 5):
        raise NotImplementedError("Native client has no legacy search_by_file interface; use scoped search")
