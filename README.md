# Casual MCP

![PyPI](https://img.shields.io/pypi/v/casual-mcp)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Casual MCP** is a Python framework for building, evaluating, and serving LLMs with tool-calling capabilities using [Model Context Protocol (MCP)](https://modelcontextprotocol.io).

## Features

- Multi-server MCP client using [FastMCP](https://github.com/jlowin/fastmcp)
- OpenAI, Ollama, and Anthropic provider support (via [casual-llm](https://github.com/AlexStansfield/casual-llm))
- Recursive tool-calling chat loop
- Toolsets for selective tool filtering per request
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

## CLI

```bash
casual-mcp serve              # Start API server
casual-mcp servers            # List configured servers
casual-mcp models             # List configured models
casual-mcp toolsets           # Manage toolsets interactively
casual-mcp tools              # List available tools
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
from casual_mcp import McpToolChat, ModelFactory, load_config, load_mcp_client

config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)

model_factory = ModelFactory(config)
llm_model = model_factory.get_model("gpt-4.1")

chat = McpToolChat(mcp_client, llm_model)
messages = [
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="What time is it?")
]
response = await chat.chat(messages)
```

See [Programmatic Usage Guide](docs/programmatic-usage.md) for `McpToolChat`, usage statistics, toolsets, and common patterns.

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
