# Programmatic Usage

Import and use the core framework in your own Python code.

## Quick Example

```python
from casual_llm import SystemMessage, UserMessage
from casual_mcp import McpToolChat, load_config

config = load_config("casual_mcp_config.json")
chat = McpToolChat.from_config(config)

messages = [
    SystemMessage(content="You are a tool calling assistant."),
    UserMessage(content="Will I need an umbrella in London today?")
]
response_messages = await chat.chat(messages, model="gpt-4.1-nano")
```

## Core Components

### McpToolChat

Orchestrates LLM interaction with tools using a recursive loop.

**`from_config()` (recommended)** — builds all dependencies from a `Config` object:

```python
from casual_mcp import McpToolChat, load_config

config = load_config("casual_mcp_config.json")
chat = McpToolChat.from_config(config, system="You are a helpful assistant.")

# Select model at call time
response = await chat.chat(messages, model="gpt-4.1")

# Override system prompt per call
response = await chat.chat(messages, model="gpt-4.1", system="Be concise.")
```

A single `McpToolChat` instance can serve multiple models — pass the model name to each `chat()` call.

**Full message control:**

```python
from casual_llm import SystemMessage, UserMessage

messages = [
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="What time is it in London?")
]
response = await chat.chat(messages, model="gpt-4.1")
```

### Advanced: Manual Construction

For full control over dependencies (custom tool cache, pre-built model, etc.):

```python
from casual_mcp import McpToolChat, ModelFactory, load_config, load_mcp_client
from casual_mcp.tool_cache import ToolCache

config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)
tool_cache = ToolCache(mcp_client)
model_factory = ModelFactory(config)
llm_model = model_factory.get_model("gpt-4.1")

chat = McpToolChat(
    mcp_client,
    system="You are a helpful assistant.",
    tool_cache=tool_cache,
    model_factory=model_factory,
)
response = await chat.chat(messages, model="gpt-4.1")
# or pass a Model instance directly:
response = await chat.chat(messages, model=llm_model)
```

Note: tool discovery is only available via `from_config()`. Manual construction does not support discovery.

### ModelFactory

Creates LLM clients and models from casual-llm based on config. Clients are cached by name, models by name.

```python
from casual_mcp import ModelFactory

model_factory = ModelFactory(config)
llm_model = model_factory.get_model("gpt-4.1")
```

### load_config / load_mcp_client

```python
from casual_mcp import load_config, load_mcp_client

config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)
```

## Usage Statistics

After calling `chat()`, retrieve usage statistics via `get_stats()`:

```python
response = await chat.chat(messages, model="gpt-4.1")
stats = chat.get_stats()

# Token usage (accumulated across all LLM calls)
stats.tokens.prompt_tokens      # Input tokens
stats.tokens.completion_tokens  # Output tokens
stats.tokens.total_tokens       # Total

# Tool call stats
stats.tool_calls.by_tool   # {"math_add": 2, "get_time": 1}
stats.tool_calls.by_server # {"math": 2, "time": 1}
stats.tool_calls.total     # Total tool calls

# LLM call count
stats.llm_calls  # 1 = no tools, 2+ = tool loop iterations
```

Stats reset at the start of each `chat()` call.

## Response Structure

`chat()` returns a list of `ChatMessage` objects:

```python
response_messages = await chat.chat(messages, model="gpt-4.1")
# Returns: list[ChatMessage]

# Get final answer
final_answer = response_messages[-1].content

# Check for tool calls
for msg in response_messages:
    if hasattr(msg, 'tool_calls') and msg.tool_calls:
        for tool_call in msg.tool_calls:
            print(f"Called: {tool_call.function.name}")
```

Message types:
- `AssistantMessage`: LLM's response (content + optional tool_calls)
- `ToolResultMessage`: Result from tool execution

## Using Toolsets

Limit which tools are available for a specific request:

```python
from casual_mcp.models import ToolSetConfig, ExcludeSpec

# Define a toolset
toolset = ToolSetConfig(
    description="Math and time tools only",
    servers={
        "math": True,                              # All tools
        "time": ["current_time", "add_days"],      # Specific tools
        "words": ExcludeSpec(exclude=["random"]),  # Exclude some
    }
)

# Use with chat()
response = await chat.chat(messages, model="gpt-4.1", tool_set=toolset)
```

## Message Types

Exported from `casual_llm` (re-exported from `casual_mcp.models`):

```python
from casual_llm import SystemMessage, UserMessage, AssistantMessage, ToolResultMessage

messages = [
    SystemMessage(content="You are a friendly assistant."),
    UserMessage(content="What is the time?")
]
```

## Config Types

```python
from casual_mcp.models import (
    McpClientConfig,
    McpModelConfig,
    StdioServerConfig,
    RemoteServerConfig,
    ToolSetConfig,
    ExcludeSpec,
    ChatStats,
    TokenUsageStats,
    ToolCallStats,
)
```

## Common Patterns

### Models Without Native Tool Support

Use Jinja2 templates to format tools in the system prompt:

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

Create `prompt-templates/custom-tool-format.j2`:

```jinja2
You have access to these tools:

{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
  Parameters: {{ tool.inputSchema.properties | tojson }}
{% endfor %}

To use a tool, respond with JSON: {"tool": "tool_name", "args": {...}}
```

When using `from_config()`, the template is resolved automatically when you pass the model name to `chat()`. An explicit `system` parameter always takes precedence over the template.

### Tool Result Formatting

Control how results are presented to the LLM:

```bash
export TOOL_RESULT_FORMAT=result              # Raw result
export TOOL_RESULT_FORMAT=function_result     # "get_weather → 72°F"
export TOOL_RESULT_FORMAT=function_args_result # "get_weather(location='London') → 15°C"
```

### Multi-Turn Conversations

Manage your own message history for multi-turn conversations:

```python
messages = []
messages.append(UserMessage(content="What's the weather?"))
response_msgs = await chat.chat(messages, model="gpt-4.1")
messages.extend(response_msgs)

messages.append(UserMessage(content="How about tomorrow?"))
response_msgs = await chat.chat(messages, model="gpt-4.1")
```

### Tool Cache

Tools are cached for 30 seconds by default. Configure with `MCP_TOOL_CACHE_TTL`:

```bash
export MCP_TOOL_CACHE_TTL=0   # Cache indefinitely
export MCP_TOOL_CACHE_TTL=5   # 5-second refresh
```
