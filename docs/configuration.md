# Configuration

Casual MCP is configured via a `casual_mcp_config.json` file that defines available clients, models, MCP tool servers, and optional toolsets.

## Example Configuration

```json
{
  "clients": {
    "openai": {
      "provider": "openai"
    },
    "ollama": {
      "provider": "ollama",
      "base_url": "http://localhost:11434"
    },
    "lm-studio": {
      "provider": "openai",
      "base_url": "http://localhost:1234/v1"
    }
  },
  "models": {
    "gpt-4.1": {
      "client": "openai",
      "model": "gpt-4.1"
    },
    "lm-qwen-3": {
      "client": "lm-studio",
      "model": "qwen3-8b",
      "template": "lm-studio-native-tools"
    },
    "ollama-qwen": {
      "client": "ollama",
      "model": "qwen2.5:7b-instruct"
    }
  },
  "servers": {
    "time": {
      "command": "python",
      "args": ["mcp-servers/time/server.py"]
    },
    "weather": {
      "url": "http://localhost:5050/mcp"
    }
  }
}
```

## Clients

Each client entry defines an LLM API connection. Multiple models can share the same client.

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | Yes | `"openai"`, `"ollama"`, or `"anthropic"` |
| `base_url` | No | Custom API endpoint URL. For Ollama: defaults to `http://localhost:11434`. For OpenAI: use for local APIs like LM Studio |
| `api_key` | No | API key override. Defaults to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` env vars |
| `timeout` | No | Request timeout in seconds (default: `60.0`) |

## Models

Each model entry references a client and specifies model-specific settings.

| Field | Required | Description |
|-------|----------|-------------|
| `client` | Yes | Name of a client defined in the `clients` section |
| `model` | Yes | Model name (e.g., `gpt-4.1`, `qwen2.5:7b-instruct`) |
| `template` | No | Jinja2 template name for system prompt formatting |
| `temperature` | No | Sampling temperature override |

## Servers

Servers can be local (stdio) or remote (HTTP/SSE).

### Local Server Config

```json
{
  "time": {
    "command": "python",
    "args": ["mcp-servers/time/server.py"],
    "env": {"KEY": "value"}
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `command` | Yes | Command to run (e.g., `python`, `npm`) |
| `args` | Yes | Arguments as a list |
| `env` | No | Environment variables for subprocess |
| `defer_loading` | No | When `true`, tools from this server are deferred for on-demand discovery (default: `false`). Requires `tool_discovery.enabled` |

### Remote Server Config

```json
{
  "weather": {
    "url": "http://localhost:5050/mcp",
    "transport": "http"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Server URL |
| `transport` | No | `http` (default), `sse`, or `streamable-http` |
| `defer_loading` | No | When `true`, tools from this server are deferred for on-demand discovery (default: `false`). Requires `tool_discovery.enabled` |

## Toolsets

Toolsets define named collections of tools for selective filtering per request.

```json
{
  "tool_sets": {
    "basic": {
      "description": "Basic tools for time and math",
      "servers": {
        "math": true,
        "time": ["current_time"]
      }
    },
    "research": {
      "description": "Research tools for weather and words",
      "servers": {
        "weather": true,
        "words": { "exclude": ["random_word"] },
        "fetch": true
      }
    }
  }
}
```

### Tool Specification Forms

| Form | Meaning | Example |
|------|---------|---------|
| `true` | All tools from the server | `"math": true` |
| `["tool1", "tool2"]` | Only these specific tools | `"time": ["current_time", "add_days"]` |
| `{ "exclude": ["tool1"] }` | All tools except these | `"words": { "exclude": ["random_word"] }` |

## System Prompt Templates

System prompts are [Jinja2](https://jinja.palletsprojects.com) templates in the `prompt-templates/` directory. They're useful for models without native tool support.

Templates receive the `tools` variable containing available tool definitions:

```jinja2
{# prompt-templates/example_prompt.j2 #}
Here is a list of functions in JSON format that you can invoke:
[
{% for tool in tools %}
  {
    "name": "{{ tool.name }}",
    "description": "{{ tool.description }}",
    "parameters": {
    {% for param_name, param in tool.inputSchema.items() %}
      "{{ param_name }}": {
        "description": "{{ param.description }}",
        "type": "{{ param.type }}"{% if param.default is defined %},
        "default": "{{ param.default }}"{% endif %}
      }{% if not loop.last %},{% endif %}
    {% endfor %}
    }
  }{% if not loop.last %},{% endif %}
{% endfor %}
]
```

Reference templates in model config:

```json
{
  "models": {
    "custom-model": {
      "client": "ollama",
      "model": "some-model:7b",
      "template": "custom-tool-format"
    }
  }
}
```

## Programmatic Config Building

Use typed models to build configs programmatically:

```python
from casual_mcp.models import (
    McpClientConfig,
    McpModelConfig,
    StdioServerConfig,
    RemoteServerConfig,
    ToolSetConfig,
    ExcludeSpec,
)

# Clients
openai_client = McpClientConfig(provider="openai")
ollama_client = McpClientConfig(
    provider="ollama",
    base_url="http://localhost:11434",
)

# Models
gpt_model = McpModelConfig(client="openai", model="gpt-4.1")
ollama_model = McpModelConfig(
    client="ollama",
    model="qwen2.5:7b-instruct",
)

# Servers
local_server = StdioServerConfig(command="python", args=["time/server.py"])
remote_server = RemoteServerConfig(url="http://localhost:5050/mcp")

# Toolsets
toolset = ToolSetConfig(
    description="Research tools",
    servers={
        "weather": True,
        "time": ["current_time"],
        "words": ExcludeSpec(exclude=["random_word"]),
    }
)
```

## Tool Discovery

When you connect many MCP servers, the total tool count can overwhelm the LLM's context. Tool discovery defers loading tools from specific servers, making them available on demand via a synthetic `search-tools` tool.

Add a `tool_discovery` section to your config and set `defer_loading: true` on servers whose tools should be deferred:

```json
{
  "servers": {
    "core-tools": {
      "command": "python",
      "args": ["servers/core.py"]
    },
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

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `enabled` | No | `false` | Master switch for tool discovery |
| `defer_all` | No | `false` | Defer all servers regardless of per-server `defer_loading` |
| `max_search_results` | No | `5` | Maximum tools returned per `search-tools` call |

See the [Tool Discovery](../CLAUDE.md#tool-discovery) section in the project docs for full details on how it works.

## Legacy Config Migration

Configs using the old format (with `provider` and `endpoint` directly in model entries) can be migrated using `casual-mcp migrate-config`.
