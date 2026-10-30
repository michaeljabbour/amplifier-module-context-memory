"""
Context Memory Module

Injects relevant memories at session start using progressive disclosure.
Provides observation index with token estimates for cost-aware retrieval.

Usage:
    context = MemoryContextProvider(store)
    injected = await context.get_context(project="my-project")
"""

import logging
from typing import Any

from .manager import MemoryContextManager
from .provider import MemoryContextProvider, create_provider

logger = logging.getLogger(__name__)

__all__ = ["MemoryContextManager", "MemoryContextProvider", "create_provider", "mount"]


async def mount(coordinator: Any, config: dict[str, Any] | None = None):
    """Mount the memory-injecting context manager at ``context``.

    Config (all optional):
        db_path: SQLite path for the memory store (default ~/.amplifier/memories.db)
        max_memories: store cap (default 1000)
        project: project filter for retrieval
        index_limit / lookback_days / token_budget: provider tuning
        inject: set False to mount without injecting memories
        store: pre-built store object (takes precedence over db_path)
    """
    config = config or {}
    store = config.get("store")
    if store is None:
        try:
            from amplifier_module_tool_memory.store import MemoryStore

            store = MemoryStore(
                db_path=config.get("db_path"),
                max_memories=config.get("max_memories", 1000),
            )
        except Exception:
            logger.exception("context-memory: memory store unavailable; mounting without memory injection")

    provider = None
    if store is not None:
        tuning = {k: config[k] for k in ("index_limit", "lookback_days", "token_budget") if k in config}
        provider = create_provider(store, **tuning)

    manager = MemoryContextManager(
        provider, project=config.get("project"), inject=config.get("inject", True)
    )
    await coordinator.mount("context", manager)
    logger.info("Mounted MemoryContextManager (store=%s)", "yes" if provider else "none")
