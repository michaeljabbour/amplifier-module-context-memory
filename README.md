# amplifier-module-context-memory

Amplifier context module that injects relevant memories at session start using progressive disclosure.

## Features

- **Progressive Disclosure**: Index view with token estimates for cost-aware retrieval
- **Session Summary Injection**: Shows last session's request/completed/learned
- **Relevance Ranking**: Ranks observations by relevance to current prompt
- **Token Budget Management**: Fits observations within configurable budget
- **On-Demand Retrieval**: Full memory details retrieved when needed

## Installation

```yaml
# Merge into the intended bundle; keep its orchestrator/providers.
session:
  context:
    module: context-memory
    source: git+https://github.com/michaeljabbour/amplifier-module-context-memory@30294227d6fe2bd1d5d991e709d7675ed19cb514
    config:
      backend: native
      native_wing: my-authorized-wing
      allow_daemon_start: true
```

Amplifier loads this module from `session.context`; `session.memory_context` is
not a context-manager slot. This selects the session’s one context manager.
Replace the example wing with an existing scope the host is authorized to read.
Set `allow_daemon_start: true` only when the host permits the dependency’s daemon
lifecycle; a host-provided client is the alternative described below.

The full commit pin includes the fixed mount and native/legacy compatibility.
The historical `v0.1.0` tag predates those fixes and has not been moved. The pin
selects this module’s source; resolve and pin its tool-memory dependency separately.

## Configuration

The dependency has two distinct APIs. Older releases provide a concrete SQLite
`MemoryStore`; native releases expose a write-store protocol and a separate
`MemoryClient`. The module does not instantiate that protocol or silently mount
without retrieval when the configured backend is unavailable.

For the native dependency, configure an explicit wing (and optional room):

```yaml
session:
  context:
    module: context-memory
    config:
      backend: native
      native_wing: my-authorized-wing
      native_room: my-authorized-room  # optional
      allow_daemon_start: true
      index_limit: 50
      token_budget: 2000
```

`allow_daemon_start: true` explicitly permits calling tool-memory's existing
`ensure_daemon()` factory, which may start, recover or replace its daemon under
the dependency's policy. The default never calls this factory. A host can instead
pass its existing `native_client` object programmatically; that path does not
discover credentials, create a client or start a daemon. The client owns transport
and authorization. Wing/room selection requests scope; it is not access control.
No model provider or embedding service is started by this adapter.

Native context uses the real room index (abstracts and overviews), not fabricated
legacy observations or session summaries. Legacy `project`, `db_path`,
`max_memories` and `lookback_days` options are rejected for native use. Native
`get_relevant_memories()` returns the client's `{results, degraded, ...}` mapping
so degradation is retained. Legacy observation-ID and file-specific lookups are
explicitly unsupported on that backend. Native read failures leave the session's
message history intact and set `MemoryContextManager.memory_status` to
`unavailable`; successful empty retrieval is a separate `available` result.

With a compatible legacy concrete SQLite dependency, these existing options
remain supported (or pass a prebuilt `store` implementing
`get_context_for_session` programmatically). Replace the context `config` mapping
with this legacy configuration:

```yaml
session:
  context:
    module: context-memory
    config:
      backend: legacy
      index_limit: 50  # Maximum observations in index
      lookback_days: 90  # How far back to look
      token_budget: 2000  # Token budget for memory context
```

Set the actual boolean `inject: false` to disable injection without opening a
store or starting a daemon. Strings such as `"false"` are rejected.

Offline tests replace native transport and daemon factory calls with fixtures.
They exercise the installed dependency's actual client API without starting a
service. Real SQLite integration tests run only when that legacy API is installed;
skips are reported rather than substituting an old package for a native result.

## Progressive Disclosure Layers

### Layer 1: Index View
Lightweight list injected at session start:
- Observation title and subtitle
- Type (bugfix, feature, discovery, etc.)
- Token estimate for full content
- Instruction to use `get_memory(id)` for details

### Layer 2: Full Details
Retrieved on-demand when AI needs specific observation:
- Complete content/narrative
- Facts and concepts
- Files read/modified
- Session and project context

## Methods

| Method | Description |
|--------|-------------|
| `get_context()` | Get index + summary for session start |
| `get_relevant_memories(query)` | Search for relevant memories |
| `get_memory_by_id(id)` | Get full details for specific memory |
| `get_file_context(path)` | Get memories related to a file |

## Requirements

- Python 3.11+
- amplifier-core

## License

MIT License - See LICENSE file
