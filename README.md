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
# Via source in bundle.yaml
session:
  memory_context:
    module: context-memory
    source: git+https://github.com/michaeljabbour/amplifier-module-context-memory@v0.1.0
```

## Configuration

```yaml
session:
  memory_context:
    module: context-memory
    config:
      index_limit: 50  # Maximum observations in index
      lookback_days: 90  # How far back to look
      token_budget: 2000  # Token budget for memory context
```

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
