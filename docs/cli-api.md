# CLI & API Reference

## CLI Commands

### `casual-mcp serve`

Start the API server.

```bash
casual-mcp serve --host 0.0.0.0 --port 8000
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Host to bind |
| `--port` | `8000` | Port to serve on |

### `casual-mcp servers`

List configured MCP servers.

```
$ casual-mcp servers
┏━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━┓
┃ Name    ┃ Type   ┃ Command / Url                 ┃ Env ┃
┡━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━┩
│ math    │ local  │ mcp-servers/math/server.py    │     │
│ time    │ local  │ mcp-servers/time-v2/server.py │     │
│ weather │ remote │ https://localhost:3000/mcp    │     │
└─────────┴────────┴───────────────────────────────┴─────┘
```

### `casual-mcp models`

List configured models.

```
$ casual-mcp models
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name              ┃ Provider ┃ Model                     ┃ Endpoint               ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ gpt-4.1           │ openai   │ gpt-4.1                   │                        │
│ lm-qwen           │ openai   │ qwen3-8b                  │ http://localhost:1234  │
└───────────────────┴──────────┴───────────────────────────┴────────────────────────┘
```

### `casual-mcp toolsets`

Interactive toolset management - create, edit, and delete toolsets.

```
$ casual-mcp toolsets
? Toolsets:
❯ basic - Basic tools for time and math (math, time)
  research - Research tools (weather, words, fetch)
  ──────────────
  ➕ Create new toolset
  ❌ Exit
```

Selecting a toolset shows details and actions:

```
basic
Description: Basic tools for time and math
Servers:
  math: [all tools]
  time: current_time

? Action:
❯ ✏️  Edit
  🗑️  Delete
  ← Back
```

### `casual-mcp tools`

List available tools from all connected MCP servers.

---

## API Endpoints

### Start the Server

```bash
casual-mcp serve --host 0.0.0.0 --port 8000
```

### POST /chat

Send full message history for a chat completion.

**Request:**

```json
{
    "model": "gpt-4.1-nano",
    "messages": [
        {"role": "user", "content": "What does consistent mean?"}
    ],
    "include_stats": true,
    "tool_set": "research"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `model` | Yes | LLM model to use |
| `messages` | Yes | List of chat messages |
| `include_stats` | No | Include usage statistics (default: `false`) |
| `tool_set` | No | Name of toolset to limit available tools |

**Response with stats:**

```json
{
    "messages": [...],
    "response": "Consistent means...",
    "stats": {
        "tokens": {
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "total_tokens": 225
        },
        "tool_calls": {
            "by_tool": {"words_define": 1},
            "by_server": {"words": 1},
            "total": 1
        },
        "llm_calls": 2
    }
}
```

### POST /generate

Send a prompt with optional session management.

**Request:**

```json
{
    "model": "gpt-4o-mini",
    "prompt": "What does consistent mean?",
    "session_id": "my-session",
    "include_stats": true,
    "tool_set": "research"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `model` | Yes | LLM model to use |
| `prompt` | Yes | User prompt |
| `session_id` | No | Session ID for context continuity |
| `include_stats` | No | Include usage statistics (default: `false`) |
| `tool_set` | No | Name of toolset to limit available tools |

### GET /generate/session/{session_id}

Retrieve all messages from a session.

### GET /toolsets

List all available toolsets.

**Response:**

```json
{
    "basic": {
        "description": "Basic tools for time and math",
        "servers": ["math", "time"]
    },
    "research": {
        "description": "Research tools",
        "servers": ["weather", "words", "fetch"]
    }
}
```
