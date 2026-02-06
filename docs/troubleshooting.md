# Troubleshooting

## Tool Not Found

If you see errors about tools not being found:

1. **Check MCP servers are running**: `casual-mcp servers`
2. **List available tools**: `casual-mcp tools`
3. **Check tool cache TTL**: Tools are cached for 30 seconds by default. Wait or restart if you just added a server.
4. **Verify server config**: Ensure `command`, `args`, or `url` are correct in your config

## Provider Initialization Issues

### OpenAI Provider

```bash
# Ensure API key is set (even for local APIs)
export OPENAI_API_KEY=your-key-here

# For local OpenAI-compatible APIs (LM Studio, etc):
export OPENAI_API_KEY=dummy-key  # Can be any string
```

### Ollama Provider

```bash
# Check Ollama is running
curl http://localhost:11434/api/version

# Ensure model is pulled
ollama pull qwen2.5:7b-instruct
```

## Cache Refresh Behavior

Tools are cached with a 30-second TTL by default. If you add/remove MCP servers:

| Option | How |
|--------|-----|
| Wait for auto-refresh | 30 seconds |
| Restart application | Immediate |
| Indefinite caching | `MCP_TOOL_CACHE_TTL=0` |
| Shorter TTL | `MCP_TOOL_CACHE_TTL=5` for 5-second refresh |

## Common Configuration Errors

### Missing Required Fields

```json
// ❌ Wrong - missing "model" field
{
  "models": {
    "my-model": {
      "provider": "openai"
    }
  }
}

// ✅ Correct
{
  "models": {
    "my-model": {
      "provider": "openai",
      "model": "gpt-4.1"
    }
  }
}
```

### Invalid Provider

```json
// ❌ Wrong - unsupported provider
{
  "models": {
    "my-model": {
      "provider": "anthropic",
      "model": "claude-3"
    }
  }
}

// ✅ Correct - use "openai" or "ollama"
{
  "models": {
    "openai-model": {
      "provider": "openai",
      "model": "gpt-4.1"
    },
    "ollama-model": {
      "provider": "ollama",
      "model": "qwen2.5:7b-instruct"
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | Required for OpenAI provider (any string for local APIs) |
| `TOOL_RESULT_FORMAT` | `result` | Format: `result`, `function_result`, `function_args_result` |
| `MCP_TOOL_CACHE_TTL` | `30` | Cache TTL in seconds (0 for indefinite) |
| `LOG_LEVEL` | `INFO` | Logging level |
