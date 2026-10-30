"""Mount-contract tests using a real MemoryStore (temp SQLite) and a minimal fake coordinator."""

import pytest

from amplifier_module_context_memory import MemoryContextManager, mount

pytest.importorskip("amplifier_module_tool_memory")
from amplifier_module_tool_memory.store import MemoryStore  # noqa: E402
legacy_store_available = not getattr(MemoryStore, "_is_protocol", False) and callable(getattr(MemoryStore, "get_context_for_session", None))


class FakeCoordinator:
    def __init__(self):
        self.mounted = {}

    async def mount(self, point, obj, name=None):
        self.mounted[point] = obj


@pytest.mark.asyncio
@pytest.mark.skipif(not legacy_store_available, reason="Installed tool-memory exposes native API; tested separately with its real MemoryClient")
async def test_mount_registers_context_manager_with_no_api_key(tmp_path, monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    db = tmp_path / "mem.db"
    MemoryStore(db_path=db).add(
        content="Use FTS5 for local retrieval", type="decision", title="Local retrieval decision"
    )

    coord = FakeCoordinator()
    await mount(coord, {"db_path": str(db)})

    ctx = coord.mounted["context"]
    assert isinstance(ctx, MemoryContextManager)
    await ctx.add_message({"role": "system", "content": "sys"})
    await ctx.add_message({"role": "user", "content": "hi"})

    msgs = await ctx.get_messages_for_request()
    assert [m["role"] for m in msgs] == ["system", "system", "user"]
    assert "Local retrieval decision" in msgs[1]["content"]
    # history itself is not mutated
    assert len(await ctx.get_messages()) == 2


@pytest.mark.asyncio
@pytest.mark.skipif(not legacy_store_available, reason="Installed tool-memory exposes native API; tested separately with its real MemoryClient")
async def test_mount_empty_store_and_inject_disabled(tmp_path):
    coord = FakeCoordinator()
    await mount(coord, {"db_path": str(tmp_path / "empty.db")})
    ctx = coord.mounted["context"]
    await ctx.add_message({"role": "user", "content": "hi"})
    assert await ctx.get_messages_for_request() == [{"role": "user", "content": "hi"}]

    coord2 = FakeCoordinator()
    await mount(coord2, {"db_path": str(tmp_path / "empty.db"), "inject": False})
    assert coord2.mounted["context"].inject is False


@pytest.mark.asyncio
async def test_mount_survives_retrieval_failure():
    class Boom:
        def get_context_for_session(self, **kw):
            raise RuntimeError("db down")

    coord = FakeCoordinator()
    await mount(coord, {"store": Boom()})
    ctx = coord.mounted["context"]
    await ctx.add_message({"role": "user", "content": "x"})
    assert await ctx.get_messages_for_request() == [{"role": "user", "content": "x"}]
    assert ctx.memory_status == {"state": "unavailable", "reason": "retrieval_failed"}


def test_entry_point_targets_mount():
    import re
    from pathlib import Path

    text = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert re.search(r'context-memory = "amplifier_module_context_memory:mount"', text)
