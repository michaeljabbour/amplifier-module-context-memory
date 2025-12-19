"""
Memory Context Provider

Implements progressive disclosure for memory injection at session start.
Inspired by claude-mem's context injection patterns.

Progressive Disclosure Layers:
1. Index View: Lightweight list with title, subtitle, token estimates
2. Full Details: Complete observation content retrieved on demand

This approach minimizes token usage while maximizing context relevance.
"""

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MemoryContextProvider:
    """
    Context provider that injects relevant memories at session start.
    
    Implements Amplifier Context protocol:
    - name: Provider identifier
    - get_context(params): Returns context to inject into prompt
    """
    
    # Default configuration
    DEFAULT_INDEX_LIMIT = 50
    DEFAULT_LOOKBACK_DAYS = 90
    DEFAULT_TOKEN_BUDGET = 2000
    
    def __init__(
        self,
        store: Any,  # MemoryStore from tool-memory
        index_limit: int = DEFAULT_INDEX_LIMIT,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ):
        """
        Initialize the memory context provider.
        
        Args:
            store: MemoryStore instance
            index_limit: Maximum observations in index
            lookback_days: How far back to look for observations
            token_budget: Approximate token budget for context
        """
        self.store = store
        self.index_limit = index_limit
        self.lookback_days = lookback_days
        self.token_budget = token_budget
    
    @property
    def name(self) -> str:
        return "memory_context"
    
    async def get_context(
        self,
        project: Optional[str] = None,
        include_summary: bool = True,
        include_index: bool = True,
        user_prompt: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Get context for injection at session start.
        
        Args:
            project: Filter by project
            include_summary: Include last session summary
            include_index: Include observation index
            user_prompt: Current user prompt (for relevance matching)
            **kwargs: Additional parameters
            
        Returns:
            Context dict with 'content' (formatted text) and 'metadata'
        """
        context_parts = []
        metadata = {
            "provider": self.name,
            "project": project,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Get context from store
        store_context = self.store.get_context_for_session(
            project=project,
            limit=self.index_limit,
            include_summaries=include_summary,
            days=self.lookback_days,
        )
        
        # Add last session summary
        if include_summary and "last_summary" in store_context:
            summary = store_context["last_summary"]
            context_parts.append(self._format_summary(summary))
            metadata["has_summary"] = True
        
        # Add observation index
        if include_index and store_context.get("observations"):
            observations = store_context["observations"]
            
            # If user prompt provided, try to rank by relevance
            if user_prompt:
                observations = self._rank_by_relevance(observations, user_prompt)
            
            # Fit within token budget
            observations = self._fit_token_budget(observations)
            
            context_parts.append(self._format_index(observations))
            metadata["observation_count"] = len(observations)
            metadata["total_observations"] = store_context.get("observation_count", 0)
        
        # Combine into final context
        content = "\n\n".join(context_parts) if context_parts else ""
        
        return {
            "content": content,
            "metadata": metadata,
        }
    
    def _format_summary(self, summary: dict) -> str:
        """Format session summary for injection."""
        parts = ["## Last Session Summary"]
        
        if summary.get("request"):
            parts.append(f"**Request:** {summary['request']}")
        
        if summary.get("completed"):
            parts.append(f"**Completed:** {summary['completed']}")
        
        if summary.get("learned"):
            parts.append(f"**Learned:** {summary['learned']}")
        
        if summary.get("next_steps"):
            parts.append(f"**Next Steps:** {summary['next_steps']}")
        
        # Files context
        files_read = summary.get("files_read", [])
        files_edited = summary.get("files_edited", [])
        
        if files_read:
            parts.append(f"**Files Read:** {', '.join(files_read[:5])}")
        if files_edited:
            parts.append(f"**Files Edited:** {', '.join(files_edited[:5])}")
        
        return "\n".join(parts)
    
    def _format_index(self, observations: list[dict]) -> str:
        """Format observation index for injection."""
        if not observations:
            return ""
        
        parts = [
            "## Observation Index",
            "_Use get_memory(id) to retrieve full details for relevant observations._",
            "",
        ]
        
        # Group by type for better organization
        by_type: dict[str, list] = {}
        for obs in observations:
            t = obs.get("type", "change")
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(obs)
        
        for obs_type, items in by_type.items():
            parts.append(f"### {obs_type.title()} ({len(items)})")
            for obs in items[:10]:  # Limit per type
                title = obs.get("title", "Untitled")
                subtitle = obs.get("subtitle", "")[:60]
                obs_id = obs.get("id", "")[:8]
                tokens = obs.get("token_estimate", 0)
                
                if subtitle:
                    parts.append(f"- **{title}** [{obs_id}...] (~{tokens} tokens)")
                    parts.append(f"  {subtitle}")
                else:
                    parts.append(f"- **{title}** [{obs_id}...] (~{tokens} tokens)")
            parts.append("")
        
        return "\n".join(parts)
    
    def _rank_by_relevance(
        self, 
        observations: list[dict], 
        user_prompt: str
    ) -> list[dict]:
        """
        Rank observations by relevance to current prompt.
        
        Simple keyword matching for now - could be enhanced with
        embeddings or more sophisticated matching.
        """
        prompt_words = set(user_prompt.lower().split())
        
        scored = []
        for obs in observations:
            # Calculate simple relevance score
            title = (obs.get("title") or "").lower()
            subtitle = (obs.get("subtitle") or "").lower()
            concepts = " ".join(obs.get("concepts", [])).lower()
            
            text = f"{title} {subtitle} {concepts}"
            text_words = set(text.split())
            
            # Count overlapping words
            overlap = len(prompt_words & text_words)
            
            # Boost for certain types
            type_boost = {
                "bugfix": 1.5,
                "decision": 1.3,
                "discovery": 1.2,
                "feature": 1.1,
            }.get(obs.get("type", ""), 1.0)
            
            score = overlap * type_boost
            scored.append((score, obs))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [obs for _, obs in scored]
    
    def _fit_token_budget(self, observations: list[dict]) -> list[dict]:
        """
        Trim observations to fit within token budget.
        
        Uses token_estimate from index view for approximation.
        """
        result = []
        total_tokens = 0
        overhead_per_obs = 20  # Estimated tokens for formatting
        
        for obs in observations:
            obs_tokens = obs.get("token_estimate", 50) + overhead_per_obs
            
            if total_tokens + obs_tokens > self.token_budget:
                break
            
            result.append(obs)
            total_tokens += obs_tokens
        
        return result
    
    async def get_relevant_memories(
        self,
        query: str,
        limit: int = 10,
        project: Optional[str] = None,
    ) -> list[dict]:
        """
        Get full memory details for relevant observations.
        
        This is layer 2 of progressive disclosure - called when
        specific memories are needed.
        
        Args:
            query: Search query
            limit: Maximum results
            project: Filter by project
            
        Returns:
            List of full memory dicts
        """
        memories = self.store.search(
            query=query,
            limit=limit,
            project=project,
        )
        return [m.to_dict() for m in memories]
    
    async def get_memory_by_id(self, memory_id: str) -> Optional[dict]:
        """
        Get full memory details by ID.
        
        Args:
            memory_id: Memory ID (can be partial, min 8 chars)
            
        Returns:
            Full memory dict or None
        """
        memory = self.store.get(memory_id)
        return memory.to_dict() if memory else None
    
    async def get_file_context(
        self,
        file_path: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Get memories related to a specific file.
        
        Useful when working on a file to understand its history.
        
        Args:
            file_path: Path to file
            limit: Maximum results
            
        Returns:
            List of memory dicts related to the file
        """
        memories = self.store.search_by_file(file_path, limit=limit)
        return [m.to_dict() for m in memories]


def create_provider(store: Any, **kwargs) -> MemoryContextProvider:
    """
    Factory function to create memory context provider.
    
    Args:
        store: MemoryStore instance
        **kwargs: Configuration options
        
    Returns:
        Configured MemoryContextProvider
    """
    return MemoryContextProvider(store, **kwargs)
