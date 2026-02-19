# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Casual MCP is a Python framework for building, evaluating, and serving LLMs with tool-calling capabilities using the Model Context Protocol (MCP). It provides a multi-server MCP client, LLM provider abstraction (via [casual-llm](https://github.com/AlexStansfield/casual-llm)), recursive tool-calling chat loop, and both CLI and API interfaces.

## Development Commands

Install for development:
```bash
uv sync --group dev
```

Run linting:
```bash
uv run ruff check src/        # Check code
uv run ruff check --fix src/  # Auto-fix issues
```

Format code:
```bash
uv run ruff format src/
```

Type checking:
```bash
uv run mypy src/
```

Run tests:
```bash
uv run pytest tests/
```

Run the CLI:
```bash
casual-mcp serve --host 0.0.0.0 --port 8000  # Start API server
casual-mcp clients                            # List configured clients
casual-mcp models                             # List configured models
casual-mcp servers                            # List configured servers
casual-mcp tools                              # List available tools
```

## Code Architecture

### Core Components

**`McpToolChat`** ([src/casual_mcp/mcp_tool_chat.py](src/casual_mcp/mcp_tool_chat.py))
- Orchestrates LLM interaction with tools using a recursive loop
- Accepts a `Model` instance from casual-llm
- Manages chat sessions (stored in-memory, for testing/development only)
- Two main methods:
  - `generate(prompt, session_id)` - Simple prompt-based interface with optional session
  - `chat(messages)` - Takes full message list for more control
- Executes tools via the MCP client and feeds results back to the LLM
- Automatically converts MCP tools to casual-llm format via `convert_tools`

**`ModelFactory`** ([src/casual_mcp/model_factory.py](src/casual_mcp/model_factory.py))
- Creates and caches LLM client and model instances from casual-llm
- Supports OpenAI, Ollama, and Anthropic providers (via casual-llm)
- Two-tier caching: clients cached by name, models cached by name
- Multiple models sharing the same client name reuse a single client connection
- Returns `Model` instances that can be used with `McpToolChat`

**`ToolCache`** ([src/casual_mcp/tool_cache.py](src/casual_mcp/tool_cache.py))
- Caches MCP tool listings to avoid repeated `list_tools` calls
- Default TTL: 30 seconds (configurable via `MCP_TOOL_CACHE_TTL` env var)
- Set TTL to 0 or negative to cache indefinitely
- Thread-safe with async lock
- Tracks version to detect when tools are refreshed

**Tool Conversion** ([src/casual_mcp/convert_tools.py](src/casual_mcp/convert_tools.py))
- Converts MCP tools to casual-llm's `Tool` format
- `tool_from_mcp(mcp_tool)` - Converts a single tool
- `tools_from_mcp(mcp_tools)` - Converts a list of tools
- Happens transparently in `McpToolChat.chat()`

**Models** ([src/casual_mcp/models/](src/casual_mcp/models/))
- Message types are imported from casual-llm: `SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `ChatMessage`, `AssistantToolCall`
- Re-exported from `casual_mcp.models` for backwards compatibility
- `config.py` - `Config`, `McpClientConfig`, and `McpModelConfig`
- `mcp_server_config.py` - `StdioServerConfig` and `RemoteServerConfig`

### Configuration File

Configuration is loaded from `casual_mcp_config.json` at the project root:

```json
{
  "clients": {
    "openai": {
      "provider": "openai"              // provider: "openai", "ollama", or "anthropic"
    },
    "ollama": {
      "provider": "ollama",
      "base_url": "http://localhost:11434"  // optional custom endpoint
    }
  },
  "models": {
    "model-name": {
      "client": "openai",              // references a key in clients
      "model": "gpt-4.1",
      "template": "template-name"      // optional, references prompt-templates/*.j2
    }
  },
  "servers": {
    "server-name": {
      "command": "python",             // for stdio servers
      "args": ["path/to/server.py"],
      "env": {"KEY": "value"}          // optional
    },
    "remote-server": {
      "url": "http://...",             // for remote servers
      "transport": "http"              // or "sse", "streamable-http"
    }
  }
}
```

### System Prompt Templates

System prompts are Jinja2 templates in [prompt-templates/](prompt-templates/):
- Templates receive the `tools` variable containing available tool definitions
- Useful for models without native tool support or custom tool formatting
- Referenced in model config via the `template` field

### API Structure

The FastAPI application ([src/casual_mcp/main.py](src/casual_mcp/main.py)) provides:
- `POST /chat` - Send full message history
- `POST /generate` - Send a prompt with optional session management
- `GET /generate/session/{session_id}` - Retrieve session messages

Sessions are stored in-memory in `mcp_tool_chat.py` and are cleared on server restart. **Important**: Sessions are for testing/development only. Production applications should manage their own message history.

## Environment Variables

**Required (depending on provider):**
- `OPENAI_API_KEY` - Required for OpenAI provider (can be any string for local OpenAI-compatible APIs)
- `ANTHROPIC_API_KEY` - Required for Anthropic provider

**Optional:**
- `TOOL_RESULT_FORMAT` - Format for tool results: `result`, `function_result`, `function_args_result` (default: `result`)
- `MCP_TOOL_CACHE_TTL` - Tool cache TTL in seconds (default: 30, set to 0 for indefinite caching)
- `LOG_LEVEL` - Logging level (default: `INFO`)

Set these in a `.env` file or export them directly.

## Project Structure

```
src/casual_mcp/
├── models/                # Pydantic models for configs, server definitions
│   ├── config.py         # Config, McpClientConfig, McpModelConfig
│   └── mcp_server_config.py  # StdioServerConfig, RemoteServerConfig
├── convert_tools.py       # MCP → casual-llm tool format conversion
├── mcp_tool_chat.py       # Core chat orchestration with tool calling
├── model_factory.py       # Creates casual-llm clients and models from config
├── tool_cache.py          # Tool listing cache with TTL
├── utils.py               # Config loading, MCP client setup, tool formatting
├── logging.py             # Logging configuration
├── cli.py                 # Typer CLI commands
└── main.py                # FastAPI application

mcp-servers/               # Example MCP server implementations
prompt-templates/          # Jinja2 templates for system prompts
```

## Key Design Patterns

1. **casual-llm Integration**: All LLM clients and models come from the casual-llm library. `ModelFactory` creates clients via `create_client()` and models via `create_model()` based on client and model config. `McpToolChat` accepts a `Model` instance from casual-llm.

2. **Tool Format Conversion**: MCP tools are automatically converted to casual-llm's `Tool` format using `convert_tools.py`. This happens transparently in `McpToolChat.chat()` before calling the model.

3. **Tool Cache with TTL**: The `ToolCache` caches tool listings with a configurable TTL (default 30 seconds). Tools are fetched from all MCP servers on first access or after TTL expires.

4. **Two-Tier Caching**: `ModelFactory` caches clients by name and models by name. Multiple models referencing the same client name reuse a single client connection.

5. **Recursive Tool Calling Loop**: `McpToolChat.chat()` implements the agentic loop:
   - Send messages + tools to LLM
   - LLM responds (possibly with tool calls)
   - Execute tool calls via MCP client
   - Add results to message history
   - Repeat until LLM provides final answer (no tool calls)

6. **Session Management**: Sessions are dictionary-based in-memory storage keyed by session ID. **Use only for testing/dev** - production apps should manage their own message history.

7. **Message Types from casual-llm**: All message types (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `ChatMessage`) are imported from casual-llm and re-exported from `casual_mcp.models` for backwards compatibility.

8. **Config Loading**: Use `load_config()` and `load_mcp_client()` from `utils.py` to bootstrap the application. Config is loaded from `casual_mcp_config.json`.
