# 🧠 Casual MCP

![PyPI](https://img.shields.io/pypi/v/casual-mcp)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Casual MCP** is a Python framework for building, evaluating, and serving LLMs with tool-calling capabilities using [Model Context Protocol (MCP)](https://modelcontextprotocol.io).
It includes:

- ✅ A multi-server MCP client using [FastMCP](https://github.com/jlowin/fastmcp)
- ✅ Provider support for OpenAI and Ollama (powered by [casual-llm](https://github.com/AlexStansfield/casual-llm))
- ✅ A recursive tool-calling chat loop
- ✅ System prompt templating with Jinja2
- ✅ A basic API exposing a chat endpoint

## ✨ Features

- Plug-and-play multi-server tool orchestration
- OpenAI and Ollama LLM providers (via casual-llm)
- Prompt templating with Jinja2
- Configurable via JSON
- CLI and API access
- Extensible architecture

## 🔧 Installation

### Uv

```bash
uv add casual-mcp
```

### Pip

```bash
pip install casual-mcp
```

Or for development:

```bash
git clone https://github.com/AlexStansfield/casual-mcp.git
cd casual-mcp
uv sync --group dev
```

## 🧩 System Prompt Templates

System prompts are defined as [Jinja2](https://jinja.palletsprojects.com) templates in the `prompt-templates/` directory.

They are used in the config file to specify a system prompt to use per model.

This allows you to define custom prompts for each model — useful when using models that do not natively support tools. Templates are passed the tool list in the `tools` variable.

```jinja2
# prompt-templates/example_prompt.j2
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

## ⚙️ Configuration File (`casual_mcp_config.json`)

📄 See the [Programmatic Usage](#-programmatic-usage) section to build configs and messages with typed models.

The CLI and API can be configured using a `casual_mcp_config.json` file that defines:

- 🔧 Available **models** and their providers
- 🧰 Available **MCP tool servers**
- 🧩 Optional tool namespacing behavior

### 🔸 Example

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

### 🔹 `models`

Each model has:

- `provider`: `"openai"` or `"ollama"`
- `model`: the model name (e.g., `gpt-4.1`, `qwen2.5:7b-instruct`)
- `endpoint`: optional custom endpoint
  - For OpenAI: custom OpenAI-compatible backends (e.g., LM Studio at `http://localhost:1234/v1`)
  - For Ollama: defaults to `http://localhost:11434` if not specified
- `template`: optional Jinja2 template name for custom system prompt formatting (useful for models without native tool support)

### 🔹 `servers`

Servers can either be local (over stdio) or remote.

#### Local Config:
- `command`: the command to run the server, e.g `python`, `npm`
- `args`: the arguments to pass to the server as a list, e.g `["time/server.py"]`
- Optional: `env`: for subprocess environments, `system_prompt` to override server prompt

#### Remote Config:
- `url`: the url of the mcp server
- Optional: `transport`: the type of transport, `http`, `sse`, `streamable-http`. Defaults to `http`

## Environmental Variables

- `OPENAI_API_KEY`: required when using the `openai` provider (can be any string when using local OpenAI-compatible APIs)
- `TOOL_RESULT_FORMAT`: adjusts the format of tool results returned to the LLM
  - Options: `result`, `function_result`, `function_args_result`
  - Default: `result`
- `MCP_TOOL_CACHE_TTL`: tool cache TTL in seconds (default: 30, set to 0 for indefinite caching)
- `LOG_LEVEL`: logging level (default: `INFO`)

You can set them using `export` or by creating a `.env` file.

## 🛠 CLI Reference

### `casual-mcp serve`
Start the API server.

**Options:**
- `--host`: Host to bind (default `0.0.0.0`)
- `--port`: Port to serve on (default `8000`)

### `casual-mcp servers`
Loads the config and outputs the list of MCP servers you have configured.

#### Example Output
```
$ casual-mcp servers
┏━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━┓
┃ Name    ┃ Type   ┃ Command / Url                 ┃ Env ┃
┡━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━┩
│ math    │ local  │ mcp-servers/math/server.py    │     │
│ time    │ local  │ mcp-servers/time-v2/server.py │     │
│ weather │ local  │ mcp-servers/weather/server.py │     │
│ words   │ remote │ https://localhost:3000/mcp    │     │
└─────────┴────────┴───────────────────────────────┴─────┘
```

### `casual-mcp models`
Loads the config and outputs the list of models you have configured.

#### Example Output
```
$ casual-mcp models
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name              ┃ Provider ┃ Model                     ┃ Endpoint               ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ lm-phi-4-mini     │ openai   │ phi-4-mini-instruct       │ http://kovacs:1234/v1  │
│ lm-hermes-3       │ openai   │ hermes-3-llama-3.2-3b     │ http://kovacs:1234/v1  │
│ lm-groq           │ openai   │ llama-3-groq-8b-tool-use  │ http://kovacs:1234/v1  │
│ gpt-4o-mini       │ openai   │ gpt-4o-mini               │                        │
│ gpt-4.1-nano      │ openai   │ gpt-4.1-nano              │                        │
│ gpt-4.1-mini      │ openai   │ gpt-4.1-mini              │                        │
│ gpt-4.1           │ openai   │ gpt-4.1                   │                        │
└───────────────────┴──────────┴───────────────────────────┴────────────────────────┘
```

## 🧠 Programmatic Usage

You can import and use the core framework in your own Python code.

### ✅ Exposed Interfaces

#### `McpToolChat`
Orchestrates LLM interaction with tools using a recursive loop.

Accepts any provider that implements the `LLMProvider` protocol from casual-llm. This means you can use casual-llm's built-in providers (OpenAI, Ollama) or create your own custom provider.

```python
from casual_llm import LLMProvider, SystemMessage, UserMessage
from casual_mcp import McpToolChat
from casual_mcp.tool_cache import ToolCache

# provider can be any object implementing the LLMProvider protocol
tool_cache = ToolCache(mcp_client)
chat = McpToolChat(mcp_client, provider, system_prompt, tool_cache=tool_cache)

# Generate method to take user prompt
response = await chat.generate("What time is it in London?")

# Generate method with session
response = await chat.generate("What time is it in London?", "my-session-id")

# Chat method that takes list of chat messages
# note: system prompt ignored if sent in messages so no need to set
chat = McpToolChat(mcp_client, provider, tool_cache=tool_cache)
messages = [
  SystemMessage(content="You are a cool dude who likes to help the user"),
  UserMessage(content="What time is it in London?")
]
response = await chat.chat(messages)
```

#### `ProviderFactory`
Instantiates LLM providers (from casual-llm) based on the selected model config.

```python
from casual_mcp import ProviderFactory

provider_factory = ProviderFactory()
provider = await provider_factory.get_provider("lm-qwen-3", model_config)
```

The factory returns an `LLMProvider` from casual-llm that can be used with `McpToolChat`.

> ℹ️ Tool catalogues are cached to avoid repeated `ListTools` calls. The cache refreshes every 30 seconds by default. Override this with the `MCP_TOOL_CACHE_TTL` environment variable (set to `0` or a negative value to cache indefinitely).

#### `load_config`
Loads your `casual_mcp_config.json` into a validated config object.

```python
from casual_mcp import load_config

config = load_config("casual_mcp_config.json")
```

#### `load_mcp_client`
Creats a multi server FastMCP client from the config object

```python
from casual_mcp import load_mcp_client

config = load_mcp_client(config)
```

#### Model and Server Configs

Exported from `casual_mcp.models`:
- `StdioServerConfig`
- `RemoteServerConfig`
- `OpenAIModelConfig`
- `OllamaModelConfig`

Use these types to build valid configs:

```python
from casual_mcp.models import OpenAIModelConfig, OllamaModelConfig, StdioServerConfig

openai_model = OpenAIModelConfig(provider="openai", model="gpt-4.1")
ollama_model = OllamaModelConfig(provider="ollama", model="qwen2.5:7b-instruct", endpoint="http://localhost:11434")
server = StdioServerConfig(command="python", args=["time/server.py"])
```

#### Chat Messages

Exported from `casual_llm` (re-exported from `casual_mcp.models` for backwards compatibility):
- `AssistantMessage`
- `SystemMessage`
- `ToolResultMessage`
- `UserMessage`
- `ChatMessage`

Use these types to build message chains:

```python
from casual_llm import SystemMessage, UserMessage

messages = [
  SystemMessage(content="You are a friendly tool calling assistant."),
  UserMessage(content="What is the time?")
]
```

### Example

```python
from casual_llm import SystemMessage, UserMessage
from casual_mcp import McpToolChat, ProviderFactory, load_config, load_mcp_client

model = "gpt-4.1-nano"
messages = [
  SystemMessage(content="""You are a tool calling assistant.
You have access to up-to-date information through the tools.
Respond naturally and confidently, as if you already know all the facts."""),
  UserMessage(content="Will I need to take my umbrella to London today?")
]

# Load the Config from the File
config = load_config("casual_mcp_config.json")

# Setup the MCP Client
mcp_client = load_mcp_client(config)

# Get the Provider for the Model
provider_factory = ProviderFactory()
provider = await provider_factory.get_provider(model, config.models[model])

# Perform the Chat and Tool calling
chat = McpToolChat(mcp_client, provider)
response_messages = await chat.chat(messages)
```

## 🏗️ Architecture Overview

Casual MCP orchestrates a flow between LLMs and MCP tool servers:

1. **MCP Client** connects to multiple tool servers (local via stdio or remote via HTTP/SSE)
2. **Tool Cache** fetches and caches available tools from all connected servers
3. **Tool Conversion** converts MCP tools to casual-llm's `Tool` format automatically
4. **ProviderFactory** creates LLM providers from casual-llm based on model config
5. **McpToolChat** orchestrates the recursive loop:
   - Sends messages + tools to LLM provider
   - LLM returns response (potentially with tool calls)
   - Executes tool calls via MCP client
   - Feeds results back to LLM
   - Repeats until LLM provides final answer

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

### Tool Conversion

MCP tools are automatically converted from MCP's format to casual-llm's `Tool` format using the `convert_tools` module. This happens transparently in `McpToolChat.chat()` via `tools_from_mcp()`.

## 📊 Response Structure

The `chat()` and `generate()` methods return a list of `ChatMessage` objects (from casual-llm):

```python
response_messages = await chat.chat(messages)
# Returns: list[ChatMessage]
# Each message can be:
# - AssistantMessage: LLM's response (content + optional tool_calls)
# - ToolResultMessage: Result from tool execution

# Access the final response:
final_answer = response_messages[-1].content

# Check for tool calls in any message:
for msg in response_messages:
    if hasattr(msg, 'tool_calls') and msg.tool_calls:
        # Message contains tool calls
        for tool_call in msg.tool_calls:
            print(f"Called: {tool_call.function.name}")
```

## 💡 Common Patterns

### Using Templates for Models Without Native Tool Support

Some models don't natively support tool calling. Use Jinja2 templates to format tools in the system prompt:

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

Create `prompt-templates/custom-tool-format.j2`:
```jinja2
You are a helpful assistant with access to these tools:

{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
  Parameters: {{ tool.inputSchema.properties | tojson }}
{% endfor %}

To use a tool, respond with JSON: {"tool": "tool_name", "args": {...}}
```

### Formatting Tool Results

Control how tool results are presented to the LLM using `TOOL_RESULT_FORMAT`:

```bash
# Just the raw result
export TOOL_RESULT_FORMAT=result

# Function name → result
export TOOL_RESULT_FORMAT=function_result
# Example: "get_weather → Temperature: 72°F"

# Function with args → result
export TOOL_RESULT_FORMAT=function_args_result
# Example: "get_weather(location='London') → Temperature: 15°C"
```

### Session Management

**Important**: Sessions are for testing/development only. In production, manage sessions in your own application.

Sessions are stored in-memory and cleared on server restart:

```python
# Using sessions for development/testing
response = await chat.generate("What's the weather?", session_id="test-123")
response = await chat.generate("How about tomorrow?", session_id="test-123")

# For production: manage your own message history
messages = []
messages.append(UserMessage(content="What's the weather?"))
response_msgs = await chat.chat(messages)
messages.extend(response_msgs)

# Next turn
messages.append(UserMessage(content="How about tomorrow?"))
response_msgs = await chat.chat(messages)
```

## 🔧 Troubleshooting

### Tool Not Found

If you see errors about tools not being found:

1. **Check MCP servers are running**: `casual-mcp servers`
2. **List available tools**: `casual-mcp tools`
3. **Check tool cache TTL**: Tools are cached for 30 seconds by default. Wait or restart if you just added a server.
4. **Verify server config**: Ensure `command`, `args`, or `url` are correct in your config

### Provider Initialization Issues

**OpenAI Provider:**
```bash
# Ensure API key is set (even for local APIs)
export OPENAI_API_KEY=your-key-here

# For local OpenAI-compatible APIs (LM Studio, etc):
export OPENAI_API_KEY=dummy-key  # Can be any string
```

**Ollama Provider:**
```bash
# Check Ollama is running
curl http://localhost:11434/api/version

# Ensure model is pulled
ollama pull qwen2.5:7b-instruct
```

### Cache Refresh Behavior

Tools are cached with a 30-second TTL by default. If you add/remove MCP servers:

- **Option 1**: Wait 30 seconds for automatic refresh
- **Option 2**: Restart the application
- **Option 3**: Set `MCP_TOOL_CACHE_TTL=0` for indefinite caching (refresh only on restart)
- **Option 4**: Set a shorter TTL like `MCP_TOOL_CACHE_TTL=5` for 5-second refresh

### Common Configuration Errors

```json
// ❌ Missing required fields
{
  "models": {
    "my-model": {
      "provider": "openai"
      // Missing "model" field!
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

// ❌ Invalid provider
{
  "models": {
    "my-model": {
      "provider": "anthropic",  // Not supported!
      "model": "claude-3"
    }
  }
}

// ✅ Supported providers
{
  "models": {
    "openai-model": {
      "provider": "openai",
      "model": "gpt-4.1"
    },
    "ollama-model": {
      "provider": "ollama",
      "model": "qwen2.5:7b"
    }
  }
}
```

## 🚀 API Usage

### Start the API Server

```bash
casual-mcp serve --host 0.0.0.0 --port 8000
```

### Chat

#### Endpoint: `POST /chat`

#### Request Body:
- `model`: the LLM model to use
- `messages`: list of chat messages (system, assistant, user, etc) that you can pass to the api, allowing you to keep your own chat session in the client calling the api

#### Example:
```
{
    "model": "gpt-4.1-nano",
    "messages": [
        {
            "role": "user",
            "content": "can you explain what the word consistent means?"
        }
    ]
}
```

### Generate

The generate endpoint allows you to send a user prompt as a string. 

It also support sessions that keep a record of all messages in the session and feeds them back into the LLM for context. Sessions are stored in memory so are cleared when the server is restarted

#### Endpoint: `POST /generate`

####  Request Body:
- `model`: the LLM model to use
- `prompt`: the user prompt 
- `session_id`: an optional ID that stores all the messages from the session and provides them back to the LLM for context

#### Example:
```
{
    "session_id": "my-session",
    "model": "gpt-4o-mini",
    "prompt": "can you explain what the word consistent means?"
}
```

### Get Session

Get all the messages from a session 

#### Endpoint: `GET /generate/session/{session_id}`


## License

This software is released under the [MIT License](LICENSE)
