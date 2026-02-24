# Changelog

## [1.0.0]

**Breaking Changes**

### Changed

- **`McpToolChat` constructor** no longer accepts `model`, `config`, or `tool_discovery_config` parameters. Use `from_config()` or pass dependencies directly.
- **`McpToolChat.chat()`** now requires a `model` parameter (string name or `Model` instance) at call time.
- **`search_tools`** synthetic tool renamed to **`search-tools`** to avoid naming conflicts with FastMCP's underscore-prefixed tool conventions.
- **FastMCP** upgraded from v2 to v3 (`fastmcp>=3.0.0`).

### Added

- **Tool discovery** -- defer tool loading and let the LLM search for tools on demand via BM25. Mark servers with `defer_loading: true` and enable `tool_discovery` in config. The LLM receives a `search-tools` meta-tool to find and load deferred tools as needed.
- **`SyntheticTool` protocol** for tools handled internally by casual-mcp (not forwarded to MCP servers). `SearchToolsTool` is the primary implementation.
- **`BM25-based tool search index`** for relevance-ranked tool discovery across tool names and descriptions.
- **`McpToolChat.from_config(config)`** classmethod that builds all dependencies (MCP client, tool cache, model factory, server names, tool discovery) from a single `Config` object.
- **Call-time model selection** -- pass `model="gpt-4.1"` or a `Model` instance to `chat()`. A single `McpToolChat` instance can serve multiple models.
- **Call-time system prompt override** -- pass `system="..."` to `chat()` to override the default. Resolution order: explicit param > model template > constructor default.
- **Discovery statistics** -- `ChatStats.discovery` tracks `search_calls` and `tools_discovered` when tool discovery is enabled.
- `ToolDiscoveryConfig` model (`enabled`, `defer_all`, `max_search_results`).
- `defer_loading` field on `StdioServerConfig` and `RemoteServerConfig`.
- CLI `tools` command shows loaded/deferred status when discovery is enabled.
- API `/chat` endpoint supports `model` and `system_prompt` fields.
- `manual_construction.py` example showing direct constructor usage.

### Removed

- **`McpToolChat.generate()`** method and all session management (`sessions` dict, `get_session()`, `get_session_messages()`, `add_messages_to_session()`). Callers should use `chat()` directly and manage their own message history.
- **`POST /generate`** and **`GET /generate/session/{session_id}`** API endpoints.
- `GenerateRequest` API model.
- `generate_weather.py`, `generate_math.py`, `generate_session.py` examples.

## [0.8.0]

**Breaking Changes**

### Changed

- Upgraded to casual-llm >= 0.6.0.
- Change config structure to match casual-llm new client/model class structure
- Improved logging across the framework.
- **ModelFactory** now accepts a `Config` object in the constructor and `get_model()` takes only a model name. Previous API: `ModelFactory()` + `get_model(name, model_config, client_configs)`. New API: `ModelFactory(config)` + `get_model(name)`.
- **API key resolution** is now handled by casual-llm via `ClientConfig.name`. Lookup order: explicit `api_key` in config > `{CLIENT_NAME.upper()}_API_KEY` env var > provider default env var (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
- **Provider strings** are passed directly to casual-llm's `ClientConfig` instead of being mapped to an enum. casual-llm handles string-to-enum coercion internally.
- `McpClientConfig.provider` type relaxed from `Literal["openai", "ollama", "anthropic"]` to `str` for forward compatibility with new providers.

### Added

- `casual-mcp migrate-config` CLI command to migrate legacy config files (with `provider`/`endpoint` in models) to the new `clients`/`models` format.

### Removed

- `PROVIDER_MAP` dict (no longer needed since casual-llm accepts provider strings).
- `API_KEY_ENV_VARS` dict and manual `os.getenv()` API key lookup (now handled by casual-llm).
- Auto-migration of legacy config at load time. Use `casual-mcp migrate-config` instead.

## [0.7.0]

### Added

- Toolsets feature for selective tool filtering per request.
- Support for metadata in tool calls.

## [0.6.0]

### Added

- Chat statistics tracking (token usage, tool calls, LLM calls).
- Structured content support in tool call results.

## [0.5.0]

### Changed

- Migrated LLM providers to [casual-llm](https://github.com/AlexStansfield/casual-llm) library.
- Introduced `ModelFactory` with client/model separation.
- Configuration split into `clients` and `models` sections.
