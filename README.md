# 🧠 Casual MCP

![PyPI](https://img.shields.io/pypi/v/casual-mcp)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Casual MCP** is a Python framework for building, evaluating, and serving LLMs with tool-calling capabilities using [Model Context Protocol (MCP)](https://modelcontextprotocol.io).  
It includes:

- ✅ A multi-server MCP client using [FastMCP](https://github.com/jlowin/fastmcp)
- ✅ Provider support for OpenAI (and OpenAI compatible APIs)
- ✅ A recursive tool-calling chat loop
- ✅ System prompt templating with Jinja2
- ✅ A basic API exposing a chat endpoint

## ✨ Features

- Plug-and-play multi-server tool orchestration
- Prompt templating with Jinja2
- Configurable via JSON
- CLI and API access
- Extensible architecture

## 🔧 Installation

```bash
pip install casual-mcp
```

Or for development:

```bash
git clone https://github.com/AlexStansfield/casual-mcp.git
cd casual-mcp
uv pip install -e .[dev]
```

## 🧩 Providers

Providers allow access to LLMs. Currently, only an OpenAI provider is supplied. However, in the model configuration, you can supply an optional `endpoint` allowing you to use any OpenAI-compatible API (e.g., LM Studio).

Ollama support is planned for a future version, along with support for custom pluggable providers via a standard interface.

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
    "lm-qwen-3": {
      "provider": "openai",
      "endpoint": "http://localhost:1234/v1",
      "model": "qwen3-8b",
      "template": "lm-studio-native-tools"
    },
    "gpt-4.1": {
        "provider": "openai",
        "model": "gpt-4.1"
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

- `provider`: `"openai"` (more to come)
- `model`: the model name (e.g., `gpt-4.1`, `qwen3-8b`)
- `endpoint`: required for custom OpenAI-compatible backends (e.g., LM Studio)
- `template`: optional name used to apply model-specific tool calling formatting

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

There are two environmental variables:
- `OPEN_AI_API_KEY`: required when using the `openai` provider, if using a local model with an openai compatible API it can be any string
- `TOOL_RESULT_FORMAT`: adjusts the format of the tool result given back to the LLM. Options are `result`, `function_result`, `function_args_result`. Defaults to `result`

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

```python
from casual_mcp import McpToolChat
from casual_mcp.tool_cache import ToolCache
from casual_mcp.models import SystemMessage, UserMessage

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
Instantiates LLM providers based on the selected model config.

```python
from casual_mcp import ProviderFactory

provider_factory = ProviderFactory(mcp_client, tool_cache=tool_cache)
provider = await provider_factory.get_provider("lm-qwen-3", model_config)
```

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

Exported models:
- StdioServerConfig
- RemoteServerConfig
- OpenAIModelConfig

Use these types to build valid configs:

```python
from casual_mcp.models import OpenAIModelConfig, StdioServerConfig

model = OpenAIModelConfig(model="llama3", endpoint="http://...")
server = StdioServerConfig(command="python", args=["time/server.py"])
```

#### Chat Messages

Exported models:
- AssistantMessage
- SystemMessage
- ToolResultMessage
- UserMessage

Use these types to build message chains:

```python
from casual_mcp.models import SystemMessage, UserMessage

messages = [
  SystemMessage(content="You are a friendly tool calling assistant."),
  UserMessage(content="What is the time?")
]
```

### Example

```python
from casual_mcp import McpToolChat, load_config, load_mcp_client, ProviderFactory
from casual_mcp.models import SystemMessage, UserMessage

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
provider_factory = ProviderFactory(mcp_client)
provider = await provider_factory.get_provider(model, config.models[model])

# Perform the Chat and Tool calling
chat = McpToolChat(mcp_client, provider)
response_messages = await chat.chat(messages)
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
