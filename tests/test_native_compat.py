"""Native/legacy API separation without daemon startup or live transport."""

from types import SimpleNamespace

import pytest

from amplifier_module_context_memory import mount


class Coordinator:
    def __init__(self):
        self.mounted = {}

    async def mount(self, point, value):
        self.mounted[point] = value


@pytest.fixture
def native_client(monkeypatch):
    module = pytest.importorskip("amplifier_module_tool_memory.client")
    # Use the installed dependency's actual public method signatures and
    # serialization into _call, replacing only its transport with a fixture.
    client = module.MemoryClient("http://127.0.0.1:1")
    calls = []

    def call(method, arguments):
        calls.append((method, arguments))
        if method == "index":
            return {"index": [{"scope": "room:fixtures", "abstract": "Local retrieval decision", "overview": "Use FTS5 for local retrieval", "source": "derived"}]}
        if method == "search":
            return {"results": [{"ref": "fixture-ref", "content": "Local retrieval decision"}], "degraded": "lexical_only"}
        raise AssertionError("Unexpected write or unsupported native operation")

    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(module, "ensure_daemon", lambda: pytest.fail("Implicit daemon startup"))
    return client, calls


@pytest.mark.asyncio
async def test_current_native_client_injects_actual_index_without_api_key(native_client, monkeypatch):
    client, calls = native_client
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing", "native_room": "fixtures"})
    manager = coordinator.mounted["context"]
    await manager.add_message({"role": "system", "content": "sys"})
    await manager.add_message({"role": "user", "content": "hi"})
    messages = await manager.get_messages_for_request()
    assert [message["role"] for message in messages] == ["system", "system", "user"]
    assert "Local retrieval decision" in messages[1]["content"]
    assert "Last Session Summary" not in messages[1]["content"]
    assert len(await manager.get_messages()) == 2
    assert manager.memory_status["state"] == "available"
    assert manager.memory_status["metadata"]["backend"] == "native"
    assert calls == [("index", {"wing": "fixture-wing", "room": "fixtures"})]


@pytest.mark.asyncio
async def test_native_search_preserves_scope_and_degradation(native_client):
    client, calls = native_client
    coordinator = Coordinator()
    await mount(coordinator, {"backend": "native", "native_client": client, "native_wing": "fixture-wing"})
    provider = coordinator.mounted["context"].provider
    result = await provider.get_relevant_memories("retrieval", limit=3)
    assert result["results"][0]["ref"] == "fixture-ref"
    assert result["degraded"] == "lexical_only"
    method, arguments = calls[-1]
    assert method == "search"
    assert arguments["query"] == "retrieval" and arguments["k"] == 3
    assert arguments["wing"] == "fixture-wing" and arguments["room"] is None


@pytest.mark.asyncio
async def test_installed_protocol_is_rejected_before_instantiation():
    store_module = pytest.importorskip("amplifier_module_tool_memory.store")
    if not getattr(store_module.MemoryStore, "_is_protocol", False):
        pytest.skip("Installed dependency is legacy; concrete SQLite mount is tested separately")
    coordinator = Coordinator()
    with pytest.raises(RuntimeError, match="no legacy SQLite factory"):
        await mount(coordinator)
    assert not coordinator.mounted


@pytest.mark.asyncio
async def test_native_requires_explicit_start_permission(native_client):
    coordinator = Coordinator()
    with pytest.raises(RuntimeError, match="explicit allow_daemon_start"):
        await mount(coordinator, {"backend": "native", "native_wing": "fixture-wing"})
    assert not coordinator.mounted


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", [False, "true", 1, None])
async def test_start_permission_is_strict_boolean(permission, native_client):
    with pytest.raises(RuntimeError, match="explicit allow_daemon_start"):
        await mount(Coordinator(), {"backend": "native", "native_wing": "fixture-wing", "allow_daemon_start": permission})


@pytest.mark.asyncio
async def test_explicit_factory_uses_dependency_but_never_runs_it_in_test(monkeypatch, native_client):
    module = pytest.importorskip("amplifier_module_tool_memory.client")
    client, calls = native_client
    starts = []
    monkeypatch.setattr(module, "ensure_daemon", lambda: starts.append(True) or client)
    coordinator = Coordinator()
    await mount(coordinator, {"backend": "native", "native_wing": "fixture-wing", "allow_daemon_start": True})
    assert starts == [True] and not calls


@pytest.mark.asyncio
async def test_unavailable_factory_fails_mount_without_claiming_success(monkeypatch, native_client):
    module = pytest.importorskip("amplifier_module_tool_memory.client")
    monkeypatch.setattr(module, "ensure_daemon", lambda: None)
    coordinator = Coordinator()
    with pytest.raises(RuntimeError, match="daemon is unavailable"):
        await mount(coordinator, {"backend": "native", "native_wing": "fixture-wing", "allow_daemon_start": True})
    assert not coordinator.mounted


@pytest.mark.asyncio
@pytest.mark.parametrize("option", [{"native_wing": ""}, {"native_wing": None}, {"native_room": ""}, {"project": "private-project"}, {"db_path": "legacy.db"}, {"lookback_days": 5}, {"index_limit": 0}, {"token_budget": True}])
async def test_invalid_native_options_fail_before_factory(option, native_client):
    config = {"backend": "native", "native_wing": "fixture-wing", "allow_daemon_start": True, **option}
    with pytest.raises(ValueError):
        await mount(Coordinator(), config)


@pytest.mark.asyncio
async def test_disabled_injection_does_not_create_store_or_daemon(monkeypatch, native_client):
    coordinator = Coordinator()
    await mount(coordinator, {"inject": False})
    manager = coordinator.mounted["context"]
    assert manager.provider is None and manager.memory_status == {"state": "disabled"}
    await manager.add_message({"role": "user", "content": "hi"})
    assert await manager.get_messages_for_request() == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_native_read_failure_retains_explicit_unavailable_status(native_client, monkeypatch):
    client, calls = native_client
    monkeypatch.setattr(client, "index", lambda **kw: (_ for _ in ()).throw(RuntimeError("fixture failure")))
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing"})
    manager = coordinator.mounted["context"]
    await manager.add_message({"role": "user", "content": "hi"})
    assert await manager.get_messages_for_request() == [{"role": "user", "content": "hi"}]
    assert manager.memory_status == {"state": "unavailable", "reason": "retrieval_failed"}
    await manager.clear()
    assert manager.memory_status == {"state": "pending"}


@pytest.mark.asyncio
async def test_native_unsupported_legacy_reads_are_explicit(native_client):
    client, calls = native_client
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing"})
    provider = coordinator.mounted["context"].provider
    with pytest.raises(NotImplementedError):
        await provider.get_memory_by_id("fixture-id")
    with pytest.raises(NotImplementedError):
        await provider.get_file_context("fixture.py")
    assert not calls


@pytest.mark.asyncio
async def test_injected_legacy_store_still_uses_legacy_contract():
    calls = []
    def context(**kw):
        calls.append(kw)
        return {"observations": [{"id": "fixture123", "type": "decision", "title": "Legacy record", "token_estimate": 10}], "observation_count": 1}
    coordinator = Coordinator()
    await mount(coordinator, {"store": SimpleNamespace(get_context_for_session=context), "project": "fixture-project"})
    manager = coordinator.mounted["context"]
    assert "Legacy record" in (await manager.get_messages_for_request())[0]["content"]
    assert calls[0]["project"] == "fixture-project"


@pytest.mark.asyncio
async def test_native_empty_index_is_available_and_does_not_create_records(native_client, monkeypatch):
    client, calls = native_client
    monkeypatch.setattr(client, "_call", lambda method, args: {"index": []})
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing"})
    manager = coordinator.mounted["context"]
    assert await manager.get_messages_for_request() == []
    assert manager.memory_status["state"] == "available"
    assert manager.memory_status["metadata"]["index_entry_count"] == 0


@pytest.mark.asyncio
async def test_native_invalid_response_is_unavailable(native_client, monkeypatch, caplog):
    client, calls = native_client
    monkeypatch.setattr(client, "_call", lambda method, args: {"index": ["not a room record"]})
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing"})
    manager = coordinator.mounted["context"]
    assert await manager.get_messages_for_request() == []
    assert manager.memory_status["state"] == "unavailable"


@pytest.mark.asyncio
async def test_native_index_display_budget_is_bounded(native_client):
    client, calls = native_client
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing", "token_budget": 3})
    result = await coordinator.mounted["context"].provider.get_context()
    assert len(result["content"].removeprefix("## Native Memory Index\n")) <= 12
    assert result["metadata"]["total_index_entries"] == 1


@pytest.mark.asyncio
async def test_native_direct_project_filter_is_rejected_before_read(native_client):
    client, calls = native_client
    coordinator = Coordinator()
    await mount(coordinator, {"native_client": client, "native_wing": "fixture-wing"})
    provider = coordinator.mounted["context"].provider
    with pytest.raises(ValueError, match="configured wing/room"):
        await provider.get_context(project="another-project")
    with pytest.raises(ValueError, match="configured wing/room"):
        await provider.get_relevant_memories("retrieval", project="another-project")
    assert not calls
