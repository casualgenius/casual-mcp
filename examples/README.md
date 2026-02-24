# Examples

Runnable examples demonstrating different features of Casual MCP. Each subfolder contains its own `config.json` and one or more scripts.

## Prerequisites

Install the project for development from the repo root:

```bash
uv sync --group dev
```

Set the required API key for your provider (e.g. `export OPENAI_API_KEY=your-key`).

## Running Examples

Change into the subfolder and run a script with `uv run`:

```bash
cd examples/tool_calling
uv run python chat_weather.py
```

Most examples default to `gpt-4.1-nano`. Override the model with the `MODEL_NAME` environment variable:

```bash
MODEL_NAME=gpt-4.1 uv run python chat_weather.py
```

## Folders

### [tool_calling/](tool_calling/)

Core tool-calling examples using `McpToolChat.from_config()`.

| Script | Description |
|--------|-------------|
| `chat_weather.py` | Asks the LLM to compare weather in two cities using weather tools |
| `chat_fetch.py` | Asks the LLM to fetch and summarise a webpage |
| `manual_construction.py` | Builds `McpToolChat` manually from individual components (`ToolCache`, `ModelFactory`, `load_mcp_client`) instead of using `from_config()` |

### [tool_discovery/](tool_discovery/)

Demonstrates deferred tool loading with the `search-tools` meta-tool.

| Script | Description |
|--------|-------------|
| `chat_with_tool_discovery.py` | Shows how tools are partitioned into loaded vs deferred sets, then lets the LLM discover and load deferred tools on demand |

The config in this folder has `tool_discovery` enabled and at least one server marked with `defer_loading: true`.

### [tool_sets/](tool_sets/)

Demonstrates restricting which tools are available to the LLM per request.

| Script | Description |
|--------|-------------|
| `chat_with_toolset.py` | Shows three ways to use toolsets: from config, programmatic creation, and exclusion-based filtering |
