"""
Context Memory Module

Injects relevant memories at session start using progressive disclosure.
Provides observation index with token estimates for cost-aware retrieval.

Usage:
    context = MemoryContextProvider(store)
    injected = await context.get_context(project="my-project")
"""

from .provider import MemoryContextProvider, create_provider

__all__ = ["MemoryContextProvider", "create_provider"]
