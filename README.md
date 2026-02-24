# Casual MCP

![PyPI](https://img.shields.io/pypi/v/casual-mcp)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Casual MCP** is a Python framework for building, evaluating, and serving LLMs with tool-calling capabilities using [Model Context Protocol (MCP)](https://modelcontextprotocol.io).

## Features

- Multi-server MCP client using [FastMCP](https://github.com/jlowin/fastmcp)
- OpenAI, Ollama, and Anthropic provider support (via [casual-llm](https://github.com/AlexStansfield/casual-llm))
- Recursive tool-calling chat loop
- Toolsets for selective tool filtering per request
- **Tool discovery** -- defer tool loading and let the LLM search for tools on demand via BM25
- Usage statistics tracking (tokens, tool calls, LLM calls)
- System prompt templating with Jinja2
- CLI and API interfaces

## Installation

```bash
# Using uv
uv add casual-mcp

# Using pip
pip install casual-mcp
```

For development:

```bash
git clone https://github.com/casualgenius/casual-mcp.git
cd casual-mcp
uv sync --group dev
```

## Quick Start

1. Create `casual_mcp_config.json`:

```json
{
  "clients": {
    "openai": { "provider": "openai" }
  },
  "models": {
    "gpt-4.1": { "client": "openai", "model": "gpt-4.1" }
  },
  "servers": {
    "time": { "command": "python", "args": ["mcp-servers/time/server.py"] }
  }
}
```

2. Set your API key: `export OPENAI_API_KEY=your-key`

3. Start the server: `casual-mcp serve`

4. Make a request:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4.1", "prompt": "What time is it?"}'
```

## Configuration

Configure clients, models, MCP servers, and toolsets in `casual_mcp_config.json`.

```json
{
  "clients": {
    "openai": { "provider": "openai" }
  },
  "models": {
    "gpt-4.1": { "client": "openai", "model": "gpt-4.1" }
  },
  "servers": {
    "time": { "command": "python", "args": ["server.py"] },
    "weather": { "url": "http://localhost:5050/mcp" }
  },
  "tool_sets": {
    "basic": { "description": "Basic tools", "servers": { "time": true } }
  }
}
```

See [Configuration Guide](docs/configuration.md) for full details on models, servers, toolsets, and templates.

## Tool Discovery

When connecting many MCP servers, the combined tool definitions can consume significant context and degrade tool selection accuracy. Tool discovery solves this by deferring tool loading -- instead of sending all tools to the LLM on every call, deferred tools are made available through a `search_tools` meta-tool that the LLM can invoke on demand.

Add `tool_discovery` to your config and mark servers with `defer_loading`:

```json
{
  "servers": {
    "core-tools": { "command": "python", "args": ["servers/core.py"] },
    "research-tools": {
      "command": "python",
      "args": ["servers/research.py"],
      "defer_loading": true
    }
  },
  "tool_discovery": {
    "enabled": true,
    "defer_all": false,
    "max_search_results": 5
  }
}
```

How it works:

1. Tools from servers with `defer_loading: true` are held back from the LLM
2. A `search_tools` tool is injected with a compressed manifest of available servers and tools
3. The LLM calls `search_tools` with a keyword query, server name, or exact tool names
4. Matched tools are loaded into the active set for the remainder of the conversation
5. Set `defer_all: true` to defer all servers without marking each individually

The CLI `tools` command shows which tools are loaded vs deferred when discovery is enabled. Stats include `search_calls` and `tools_discovered` counts.

## CLI

```bash
casual-mcp serve              # Start API server
casual-mcp servers            # List configured servers
casual-mcp clients            # List configured clients
casual-mcp models             # List configured models
casual-mcp toolsets           # Manage toolsets interactively
casual-mcp tools              # List available tools
casual-mcp migrate-config     # Migrate legacy config to new format
```

See [CLI & API Reference](docs/cli-api.md) for all commands and options.

## API

| Endpoint | Description |
|----------|-------------|
| `POST /chat` | Send message history |
| `POST /generate` | Send prompt with optional session |
| `GET /generate/session/{id}` | Get session messages |
| `GET /toolsets` | List available toolsets |

See [CLI & API Reference](docs/cli-api.md#api-endpoints) for request/response formats.

## Programmatic Usage

```python
from casual_llm import SystemMessage, UserMessage
from casual_mcp import McpToolChat, load_config

config = load_config("casual_mcp_config.json")
chat = McpToolChat.from_config(config)

messages = [
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="What time is it?")
]
response = await chat.chat(messages, model="gpt-4.1")
```

For full control you can still construct `McpToolChat` manually — see the [Programmatic Usage Guide](docs/programmatic-usage.md) for details on `from_config()`, model selection at call time, usage statistics, toolsets, and common patterns.

## Architecture

Casual MCP orchestrates LLMs and MCP tool servers in a recursive loop:

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│ MCP Servers │─────▶│  Tool Cache  │─────▶│ Tool Converter│
└─────────────┘      └──────────────┘      └─────────────┘
                            │                      │
                            ▼                      ▼
                     ┌──────────────────────────────┐
                     │     McpToolChat Loop         │
                     │                              │
                     │  LLM ──▶ Tool Calls ──▶ MCP  │
                     │   ▲                      │   │
                     │   └──────── Results ─────┘   │
                     └──────────────────────────────┘
```

1. **MCP Client** connects to tool servers (local stdio or remote HTTP/SSE)
2. **Tool Cache** fetches and caches tools from all servers
3. **ModelFactory** creates LLM clients and models from casual-llm
4. **McpToolChat** runs the recursive loop until the LLM provides a final answer

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `{CLIENT_NAME}_API_KEY` | - | API key lookup: tries `{CLIENT_NAME.upper()}_API_KEY` first, falls back to provider default (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) |
| `TOOL_RESULT_FORMAT` | `result` | `result`, `function_result`, or `function_args_result` |
| `MCP_TOOL_CACHE_TTL` | `30` | Tool cache TTL in seconds (0 = indefinite) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Troubleshooting

Common issues and solutions are covered in the [Troubleshooting Guide](docs/troubleshooting.md).

## License

[MIT License](LICENSE)
