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
- **`from_config(config)`** classmethod builds all dependencies from a `Config` object (recommended)
- Model selection at call time: `chat(messages, model="gpt-4.1")`
- System prompt resolved per-call: explicit `system` param > model template > constructor default
- Constructor takes `(mcp_client, system, tool_cache, server_names, synthetic_tools, model_factory)` — no `model` or `config`
- Tool discovery and config are wired internally by `from_config()`; manual construction does not support discovery
- One main method:
  - `chat(messages, model, system)` - Takes full message list, returns response messages
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

**Tool Discovery** ([src/casual_mcp/tool_discovery.py](src/casual_mcp/tool_discovery.py), [src/casual_mcp/search_tools_tool.py](src/casual_mcp/search_tools_tool.py))
- Enables on-demand tool loading to reduce the number of tools sent to the LLM
- Partitions tools into "loaded" (sent immediately) and "deferred" (discoverable on demand)
- Injects a synthetic `search_tools` tool that the LLM can call to find and load deferred tools
- Uses BM25 keyword search ([src/casual_mcp/tool_search_index.py](src/casual_mcp/tool_search_index.py)) for relevance-ranked discovery
- See [Tool Discovery](#tool-discovery) section below for full details

**Synthetic Tools** ([src/casual_mcp/synthetic_tool.py](src/casual_mcp/synthetic_tool.py))
- Protocol for tools handled internally by casual-mcp (not forwarded to MCP servers)
- `SyntheticTool` - Protocol defining `name`, `definition`, and `execute()` interface
- `SyntheticToolResult` - NamedTuple with `content` (str) and `newly_loaded_tools` (list of MCP tools)
- Used by the chat loop to intercept and execute special tools like `search_tools`

**Models** ([src/casual_mcp/models/](src/casual_mcp/models/))
- Message types are imported from casual-llm: `SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `ChatMessage`, `AssistantToolCall`
- Re-exported from `casual_mcp.models` for backwards compatibility
- `config.py` - `Config`, `McpClientConfig`, and `McpModelConfig`
- `mcp_server_config.py` - `StdioServerConfig` and `RemoteServerConfig`
- `tool_discovery_config.py` - `ToolDiscoveryConfig` (enabled, defer_all, max_search_results)
- `chat_stats.py` - `ChatStats`, `DiscoveryStats`, `TokenUsageStats`, `ToolCallStats`

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
      "env": {"KEY": "value"},         // optional
      "defer_loading": false           // optional, defers tools for discovery (default: false)
    },
    "remote-server": {
      "url": "http://...",             // for remote servers
      "transport": "http",             // or "sse", "streamable-http"
      "defer_loading": false           // optional, defers tools for discovery (default: false)
    }
  },
  "tool_discovery": {                  // optional, enables on-demand tool loading
    "enabled": true,
    "defer_all": false,                // treat all servers as deferred (default: false)
    "max_search_results": 5            // max tools per search query (default: 5)
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
- `GET /toolsets` - List available toolsets

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
├── models/                    # Pydantic models for configs, server definitions
│   ├── config.py             # Config, McpClientConfig, McpModelConfig
│   ├── mcp_server_config.py  # StdioServerConfig, RemoteServerConfig
│   ├── tool_discovery_config.py  # ToolDiscoveryConfig
│   ├── toolset_config.py     # ToolSetConfig, ExcludeSpec
│   └── chat_stats.py         # ChatStats, DiscoveryStats, TokenUsageStats, ToolCallStats
├── convert_tools.py           # MCP → casual-llm tool format conversion
├── mcp_tool_chat.py           # Core chat orchestration with tool calling
├── model_factory.py           # Creates casual-llm clients and models from config
├── tool_cache.py              # Tool listing cache with TTL
├── tool_discovery.py          # Tool partitioning (loaded vs deferred)
├── tool_search_index.py       # BM25-based tool search index
├── search_tools_tool.py       # SearchToolsTool synthetic tool + manifest generation
├── synthetic_tool.py          # SyntheticTool protocol for internal tools
├── tool_filter.py             # Toolset-based tool filtering
├── utils.py                   # Config loading, MCP client setup, tool formatting
├── logging.py                 # Logging configuration
├── cli.py                     # Typer CLI commands
└── main.py                    # FastAPI application

mcp-servers/                   # Example MCP server implementations
prompt-templates/              # Jinja2 templates for system prompts
```

## Key Design Patterns

1. **casual-llm Integration**: All LLM clients and models come from the casual-llm library. `ModelFactory` creates clients via `create_client()` and models via `create_model()` based on client and model config. `McpToolChat` accepts a `Model` instance or resolves model names via `ModelFactory`. The MCP client uses FastMCP 3.x.

2. **Tool Format Conversion**: MCP tools are automatically converted to casual-llm's `Tool` format using `convert_tools.py`. This happens transparently in `McpToolChat.chat()` before calling the model.

3. **Tool Cache with TTL**: The `ToolCache` caches tool listings with a configurable TTL (default 30 seconds). Tools are fetched from all MCP servers on first access or after TTL expires.

4. **Two-Tier Caching**: `ModelFactory` caches clients by name and models by name. Multiple models referencing the same client name reuse a single client connection.

5. **Recursive Tool Calling Loop**: `McpToolChat.chat()` implements the agentic loop:
   - Resolve model (from `model` param, factory, or constructor default) and system prompt
   - Send messages + tools to LLM
   - LLM responds (possibly with tool calls)
   - Execute tool calls via MCP client (or synthetic tools internally)
   - Add results to message history
   - Repeat until LLM provides final answer (no tool calls)

6. **Message Types from casual-llm**: All message types (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `ChatMessage`) are imported from casual-llm and re-exported from `casual_mcp.models` for backwards compatibility.

7. **Config Loading**: Use `load_config()` from `utils.py` to load configuration, then `McpToolChat.from_config(config)` to create a fully-wired instance. For manual setup, use `load_mcp_client()` from `utils.py`. Config is loaded from `casual_mcp_config.json`.

8. **Tool Discovery**: When many MCP servers provide tools, the full tool list can overwhelm the LLM's context. Tool discovery partitions tools into loaded (eager) and deferred sets. Deferred tools are not sent to the LLM directly; instead, a synthetic `search_tools` tool is injected that lets the LLM search for and load tools on demand. See [Tool Discovery](#tool-discovery) below.

9. **Synthetic Tool Protocol**: Internal tools that are handled by casual-mcp itself (not forwarded to MCP servers). The `SyntheticTool` protocol defines the interface; `SearchToolsTool` is the primary implementation. Synthetic tools are dispatched in the chat loop before MCP tool execution.

## Tool Discovery

Tool discovery allows you to defer loading tools from specific MCP servers, reducing the number of tool definitions sent to the LLM on each call. Instead of receiving all tools upfront, the LLM is given a `search_tools` meta-tool that it can use to find and load the tools it needs on demand.

### Why Use Tool Discovery

When you connect many MCP servers, the total number of tools can grow large. Sending all tool definitions in every LLM call:
- Consumes context window tokens
- Can confuse the LLM with too many choices
- Increases latency and cost

Tool discovery solves this by only sending frequently-used tools eagerly and making the rest available through search.

### Configuration

Add a `tool_discovery` section to `casual_mcp_config.json` and set `defer_loading: true` on servers whose tools should be deferred:

```json
{
  "clients": {
    "openai": {
      "provider": "openai"
    }
  },
  "models": {
    "gpt-4.1": {
      "client": "openai",
      "model": "gpt-4.1"
    }
  },
  "servers": {
    "core-tools": {
      "command": "python",
      "args": ["servers/core.py"]
    },
    "research-tools": {
      "command": "python",
      "args": ["servers/research.py"],
      "defer_loading": true
    },
    "data-tools": {
      "url": "http://localhost:9000",
      "transport": "streamable-http",
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

**Configuration options:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tool_discovery.enabled` | `bool` | `false` | Master switch for tool discovery |
| `tool_discovery.defer_all` | `bool` | `false` | Defer all servers regardless of per-server `defer_loading` |
| `tool_discovery.max_search_results` | `int` | `5` | Maximum tools returned per `search_tools` call (minimum: 1) |
| `servers.*.defer_loading` | `bool` | `false` | Defer tools from this specific server |

### How It Works

1. **Tool Partitioning**: When `McpToolChat.chat()` starts, `partition_tools()` splits all available MCP tools into two sets:
   - **Loaded tools**: Sent to the LLM immediately (from servers without `defer_loading`)
   - **Deferred tools**: Held back, organized by server name

2. **search_tools Injection**: If any deferred tools exist, a synthetic `search_tools` tool is automatically injected into the tool list sent to the LLM. Its description includes a manifest of all deferred servers and their tools.

3. **LLM Searches for Tools**: When the LLM needs a tool that is not in its loaded set, it calls `search_tools` with one or more of:
   - `query` (string) - BM25 keyword search across tool names and descriptions
   - `server_name` (string) - Load all tools from a specific server
   - `tool_names` (array of strings) - Load tools by exact name

4. **Dynamic Tool Expansion**: Tools found by `search_tools` are added to the loaded set for all subsequent LLM calls within the same chat session. The LLM can then call these tools normally.

5. **Statistics Tracking**: When tool discovery is enabled, `ChatStats.discovery` is populated with a `DiscoveryStats` object tracking `search_calls` and `tools_discovered`.

### The search_tools Tool

The `search_tools` tool is a synthetic tool (handled internally, not forwarded to MCP servers) that supports three search modes:

**Keyword search** (`query` parameter):
- Uses BM25 (Okapi) ranking over tool names and descriptions
- Tokenizes by splitting on whitespace and underscores for better tool name matching
- Returns up to `max_search_results` results ranked by relevance
- Falls back to token overlap counting for very small corpora where BM25 IDF produces zero scores

**Server browsing** (`server_name` parameter):
- Returns all tools from the named server
- Validates the server name and returns an error for unknown servers

**Exact name lookup** (`tool_names` parameter):
- Looks up tools by exact name
- Reports which names were not found

**Combined parameters:**
- `server_name` + `query`: Scoped keyword search within one server
- `server_name` + `tool_names`: Exact lookup filtered to one server
- `query` + `tool_names`: `tool_names` takes precedence over keyword search

The tool returns formatted details including each tool's server, description, and parameters. Tools that were already loaded in a previous search are marked as "Already loaded" in the response.

### Manifest Format

The `search_tools` tool description includes a manifest of all deferred servers and their tools. The manifest is generated by `generate_manifest()` and follows this format:

```
- server-name (N tools): tool_a, tool_b, tool_c
  Brief summary derived from tool descriptions.
- large-server (25 tools): tool_a, tool_b, tool_c, tool_d, ... and 21 more
  Summary description truncated to 80 characters...
```

For servers with more than 10 tools, only the first four tool names are shown with a count of remaining tools.

### Interaction with Toolsets

Tool discovery and toolsets work together:
- Toolset filtering is applied **before** tool discovery partitioning
- If a toolset excludes a server, none of that server's tools will be deferred or loaded
- If a toolset includes only specific tools from a deferred server, only those tools are available for discovery

### Edge Cases and Expected Behavior

**No deferred tools**: If tool discovery is enabled but no servers have `defer_loading: true` (and `defer_all` is false), all tools are loaded eagerly and `search_tools` is not injected. Discovery stats are still tracked but `search_calls` and `tools_discovered` will be 0.

**Calling a deferred tool without searching first**: If the LLM attempts to call a deferred tool that has not been loaded via `search_tools`, the chat loop returns an error message: `"Error: Tool '{name}' is not yet loaded. Use the 'search_tools' tool to discover and load it first, then call it again."`

**Tool cache refresh mid-session**: If the tool cache TTL expires and tools are refreshed during an active chat session, the discovery index is rebuilt automatically. Tools that were previously loaded via `search_tools` remain loaded even after the rebuild.

**Empty search results**: If a keyword search returns no matches, the tool returns a message like `"No tools found matching '{query}'."` The LLM can then refine its search.

**`defer_all: true`**: Overrides all per-server `defer_loading` settings. Every server's tools are deferred, so only the `search_tools` tool is available initially.

**Unknown server in tool name resolution**: If a tool's server cannot be determined from its name prefix, it is loaded eagerly (not deferred) to avoid silently hiding tools.

**Discovery disabled**: When `tool_discovery.enabled` is `false` (or the `tool_discovery` section is absent), all tools are loaded eagerly as normal. The `defer_loading` server setting is ignored.

### CLI Support

The `casual-mcp tools` command shows tool discovery status when enabled:

```bash
casual-mcp tools
```

When tool discovery is configured and enabled, the table includes a **Status** column showing either `loaded` or `deferred` for each tool. When discovery is disabled, the Status column is omitted.

### Key Source Files

| File | Description |
|------|-------------|
| `src/casual_mcp/models/tool_discovery_config.py` | `ToolDiscoveryConfig` model (enabled, defer_all, max_search_results) |
| `src/casual_mcp/tool_discovery.py` | `partition_tools()` and `build_tool_server_map()` helpers |
| `src/casual_mcp/tool_search_index.py` | `ToolSearchIndex` - BM25-based search over tool names/descriptions |
| `src/casual_mcp/search_tools_tool.py` | `SearchToolsTool` implementation and `generate_manifest()` |
| `src/casual_mcp/synthetic_tool.py` | `SyntheticTool` protocol and `SyntheticToolResult` |
| `src/casual_mcp/models/chat_stats.py` | `DiscoveryStats` (search_calls, tools_discovered) |
