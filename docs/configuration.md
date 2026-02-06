# Configuration

Casual MCP is configured via a `casual_mcp_config.json` file that defines available models, MCP tool servers, and optional toolsets.

## Example Configuration

```json
{
  "models": {
    "gpt-4.1": {
      "provider": "openai",
      "model": "gpt-4.1"
    },
    "lm-qwen-3": {
      "provider": "openai",
      "endpoint": "http://localhost:1234/v1",
      "model": "qwen3-8b",
      "template": "lm-studio-native-tools"
    },
    "ollama-qwen": {
      "provider": "ollama",
      "endpoint": "http://localhost:11434",
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

## Models

Each model entry has:

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | Yes | `"openai"` or `"ollama"` |
| `model` | Yes | Model name (e.g., `gpt-4.1`, `qwen2.5:7b-instruct`) |
| `endpoint` | No | Custom endpoint URL. For OpenAI: use for local APIs like LM Studio. For Ollama: defaults to `http://localhost:11434` |
| `template` | No | Jinja2 template name for system prompt formatting |

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
      "provider": "ollama",
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
    OpenAIModelConfig,
    OllamaModelConfig,
    StdioServerConfig,
    RemoteServerConfig,
    ToolSetConfig,
    ExcludeSpec,
)

# Models
openai_model = OpenAIModelConfig(provider="openai", model="gpt-4.1")
ollama_model = OllamaModelConfig(
    provider="ollama",
    model="qwen2.5:7b-instruct",
    endpoint="http://localhost:11434"
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
