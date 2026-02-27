# Migration Guide: 0.x to 1.0

This guide covers breaking changes when upgrading from casual-mcp 0.x to 1.0.

## Configuration

No changes to `casual_mcp_config.json` format. If you're still on the pre-0.8 format (with `provider` and `endpoint` directly in model entries), run:

```bash
casual-mcp migrate-config
```

### New: Tool Discovery

1.0 adds optional tool discovery. To use it, add `tool_discovery` to your config and set `defer_loading: true` on servers you want deferred:

```json
{
  "servers": {
    "core": { "command": "python", "args": ["core.py"] },
    "research": { "command": "python", "args": ["research.py"], "defer_loading": true }
  },
  "tool_discovery": {
    "enabled": true,
    "max_search_results": 5
  }
}
```

See [Configuration: Tool Discovery](configuration.md#tool-discovery) for details.

## API Changes

### McpToolChat Constructor

The constructor no longer accepts `model`, it is passed in the chat method instead. It's now recommended to use the `from_config` for constructing the McpToolChat.

**Before (0.x):**

```python
chat = McpToolChat(mcp_client, system="...", model=model, config=config)
response = await chat.chat(messages)
```

**After (1.0):**

```python
# Recommended: use from_config()
chat = McpToolChat.from_config(config, system="...")
response = await chat.chat(messages, model="gpt-4.1")

# Or pass dependencies directly
chat = McpToolChat(mcp_client, system="...", tool_cache=tool_cache, model_factory=model_factory)
response = await chat.chat(messages, model=model_instance)
```

### Model Selection at Call Time

`chat()` now requires a `model` parameter. Pass either a string name (resolved via `ModelFactory`) or a `Model` instance.

```python
# String name (requires model_factory or from_config)
response = await chat.chat(messages, model="gpt-4.1")

# Model instance (works with any construction method)
response = await chat.chat(messages, model=my_model)
```

### System Prompt Override

`chat()` now accepts an optional `system` parameter to override the default prompt per call:

```python
response = await chat.chat(messages, model="gpt-4.1", system="Be concise.")
```

### Session Management Removed

`generate()`, `get_session()`, `get_session_messages()`, and `add_messages_to_session()` have been removed. Manage your own message history:

```python
history = []
history.append(UserMessage(content="What's the weather?"))
response = await chat.chat(history, model="gpt-4.1")
history.extend(response)

history.append(UserMessage(content="How about tomorrow?"))
response = await chat.chat(history, model="gpt-4.1")
history.extend(response)
```

## API Endpoints

### Removed Endpoints

- `POST /generate` -- use `POST /chat` instead
- `GET /generate/session/{session_id}` -- manage sessions client-side

### Changed: POST /chat

The `model` field is now required:

```json
{
  "model": "gpt-4.1",
  "messages": [{"role": "user", "content": "Hello"}]
}
```

New optional field `system_prompt` overrides the default system prompt:

```json
{
  "model": "gpt-4.1",
  "messages": [{"role": "user", "content": "Hello"}],
  "system_prompt": "Be concise."
}
```

## Dependencies

- **FastMCP** upgraded from v2 to v3 (`fastmcp>=3.0.0`)
- **casual-llm** minimum version unchanged

## Tool Naming

The `search_tools` synthetic tool was renamed to `search-tools` to avoid conflicts with FastMCP's underscore-prefixed tool naming convention. This only affects you if you were referencing the tool name directly in code or prompts.
