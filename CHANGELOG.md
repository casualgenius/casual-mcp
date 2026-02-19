# Changelog

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
