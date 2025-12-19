"""Tests for context-memory module."""

import pytest
from unittest.mock import MagicMock

from amplifier_module_context_memory import MemoryContextProvider, create_provider


class TestMemoryContextProvider:
    """Test MemoryContextProvider functionality."""

    def test_provider_name(self):
        """Provider should have correct name."""
        store = MagicMock()
        provider = MemoryContextProvider(store)
        assert provider.name == "memory_context"

    @pytest.mark.asyncio
    async def test_get_context_empty(self):
        """Should handle empty context gracefully."""
        store = MagicMock()
        store.get_context_for_session = MagicMock(return_value={
            "observations": [],
            "observation_count": 0
        })
        
        provider = MemoryContextProvider(store)
        result = await provider.get_context()
        
        assert "content" in result
        assert "metadata" in result
        assert result["metadata"]["provider"] == "memory_context"

    @pytest.mark.asyncio
    async def test_get_context_with_summary(self):
        """Should format session summary correctly."""
        store = MagicMock()
        store.get_context_for_session = MagicMock(return_value={
            "last_summary": {
                "request": "Implement feature X",
                "completed": "Added feature X",
                "learned": "New pattern discovered",
                "next_steps": "Test the feature"
            },
            "observations": [],
            "observation_count": 0
        })
        
        provider = MemoryContextProvider(store)
        result = await provider.get_context(include_summary=True)
        
        assert "Last Session Summary" in result["content"]
        assert "Implement feature X" in result["content"]

    @pytest.mark.asyncio
    async def test_get_context_with_observations(self):
        """Should format observation index correctly."""
        store = MagicMock()
        store.get_context_for_session = MagicMock(return_value={
            "observations": [
                {
                    "id": "abc12345",
                    "type": "bugfix",
                    "title": "Fixed parsing bug",
                    "subtitle": "The parser was not handling edge cases",
                    "token_estimate": 150
                },
                {
                    "id": "def67890",
                    "type": "discovery",
                    "title": "Found config pattern",
                    "subtitle": "The config uses YAML frontmatter",
                    "token_estimate": 200
                }
            ],
            "observation_count": 2
        })
        
        provider = MemoryContextProvider(store)
        result = await provider.get_context(include_index=True)
        
        assert "Observation Index" in result["content"]
        assert "Fixed parsing bug" in result["content"]
        assert result["metadata"]["observation_count"] == 2

    def test_rank_by_relevance(self):
        """Should rank observations by prompt relevance."""
        store = MagicMock()
        provider = MemoryContextProvider(store)
        
        observations = [
            {"title": "Database migration", "subtitle": "SQL schema changes", "type": "change"},
            {"title": "API authentication", "subtitle": "JWT token handling", "type": "bugfix"},
            {"title": "User interface", "subtitle": "React component updates", "type": "feature"}
        ]
        
        ranked = provider._rank_by_relevance(observations, "Fix the JWT authentication bug")
        
        # Authentication/JWT should rank higher
        assert ranked[0]["title"] == "API authentication"

    def test_fit_token_budget(self):
        """Should trim observations to fit token budget."""
        store = MagicMock()
        provider = MemoryContextProvider(store, token_budget=200)
        
        observations = [
            {"title": "Obs 1", "token_estimate": 100},
            {"title": "Obs 2", "token_estimate": 100},
            {"title": "Obs 3", "token_estimate": 100},
            {"title": "Obs 4", "token_estimate": 100}
        ]
        
        # With overhead of 20 per obs, only 1 should fit (120 < 200 but 240 > 200)
        result = provider._fit_token_budget(observations)
        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_get_memory_by_id(self):
        """Should retrieve full memory by ID."""
        store = MagicMock()
        store.get = MagicMock(return_value=MagicMock(
            to_dict=MagicMock(return_value={
                "id": "abc12345",
                "content": "Full memory content"
            })
        ))
        
        provider = MemoryContextProvider(store)
        result = await provider.get_memory_by_id("abc12345")
        
        assert result["id"] == "abc12345"
        store.get.assert_called_with("abc12345")


class TestCreateProvider:
    """Test create_provider factory function."""

    def test_creates_provider_instance(self):
        """Factory should create MemoryContextProvider."""
        store = MagicMock()
        provider = create_provider(store)
        
        assert isinstance(provider, MemoryContextProvider)
        assert provider.store is store

    def test_accepts_config_options(self):
        """Factory should accept configuration options."""
        store = MagicMock()
        provider = create_provider(
            store,
            index_limit=100,
            lookback_days=30,
            token_budget=3000
        )
        
        assert provider.index_limit == 100
        assert provider.lookback_days == 30
        assert provider.token_budget == 3000
