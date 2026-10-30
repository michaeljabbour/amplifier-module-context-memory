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
from .native import NativeMemoryContextProvider
from .provider import MemoryContextProvider, create_provider

logger = logging.getLogger(__name__)

__all__ = ["MemoryContextManager", "MemoryContextProvider", "NativeMemoryContextProvider", "create_provider", "mount"]


async def mount(coordinator: Any, config: dict[str, Any] | None = None):
    """Mount the memory-injecting context manager at ``context``.

    Legacy concrete SQLite stores and native memory clients are separate APIs.
    Native use requires explicit scope and a host-provided client, or explicit
    permission to call the dependency's daemon-starting factory. No daemon is
    started by the default/legacy path. See README for the configuration contract.
    """
    config = config or {}
    inject = config.get("inject", True)
    if type(inject) is not bool:
        raise ValueError("context-memory inject must be a boolean")
    provider = None
    if inject:
        backend = config.get("backend", "auto")
        if backend not in {"auto", "legacy", "native"}:
            raise ValueError("context-memory backend must be auto, legacy or native")
        if config.get("store") is not None and config.get("native_client") is not None:
            raise ValueError("Choose a legacy store or native client, not both")
        if backend == "auto":
            backend = "native" if config.get("native_client") is not None else "legacy"
        if backend == "native":
            if any(config.get(key) is not None for key in ("store", "db_path", "max_memories", "project", "lookback_days")):
                raise ValueError("Native memory uses explicit wing/room scope, not legacy SQLite/project options")
            # Validate scope/options before a factory can perform any I/O.
            NativeMemoryContextProvider.validate_config(config)
            client = config.get("native_client")
            if client is None:
                if config.get("allow_daemon_start") is not True:
                    raise RuntimeError("Native memory requires native_client or explicit allow_daemon_start: true")
                try:
                    from amplifier_module_tool_memory.client import ensure_daemon
                    client = ensure_daemon()
                except Exception:
                    raise RuntimeError("Native memory client is unavailable") from None
                if client is None:
                    raise RuntimeError("Native memory daemon is unavailable")
            provider = NativeMemoryContextProvider(client, config)
        else:
            if config.get("native_client") is not None:
                raise ValueError("native_client requires the native backend")
            store = config.get("store")
            if store is None:
                from amplifier_module_tool_memory.store import MemoryStore
                if getattr(MemoryStore, "_is_protocol", False) or not callable(getattr(MemoryStore, "get_context_for_session", None)):
                    raise RuntimeError("Installed tool-memory has no legacy SQLite factory; configure backend: native with explicit native_wing and client/start permission")
                try:
                    store = MemoryStore(db_path=config.get("db_path"), max_memories=config.get("max_memories", 1000))
                except Exception:
                    raise RuntimeError("Legacy memory store is unavailable") from None
            if not callable(getattr(store, "get_context_for_session", None)):
                raise ValueError("Legacy store must implement get_context_for_session")
            tuning = {k: config[k] for k in ("index_limit", "lookback_days", "token_budget") if k in config}
            provider = create_provider(store, **tuning)

    manager = MemoryContextManager(
        provider, project=config.get("project"), inject=inject
    )
    await coordinator.mount("context", manager)
    logger.info("Mounted MemoryContextManager (memory=%s)", "pending retrieval" if provider else "disabled")
