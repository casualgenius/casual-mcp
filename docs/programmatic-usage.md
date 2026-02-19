# Programmatic Usage

Import and use the core framework in your own Python code.

## Quick Example

```python
from casual_llm import SystemMessage, UserMessage
from casual_mcp import McpToolChat, ModelFactory, load_config, load_mcp_client

model = "gpt-4.1-nano"
messages = [
    SystemMessage(content="You are a tool calling assistant."),
    UserMessage(content="Will I need an umbrella in London today?")
]

# Load config and setup
config = load_config("casual_mcp_config.json")
mcp_client = load_mcp_client(config)

# Get model and run chat
model_factory = ModelFactory(config)
llm_model = model_factory.get_model(model)

chat = McpToolChat(mcp_client, llm_model)
response_messages = await chat.chat(messages)
```

## Core Components

### McpToolChat

Orchestrates LLM interaction with tools using a recursive loop. Accepts a `Model` instance from casual-llm.

```python
from casual_llm import SystemMessage, UserMessage
from casual_mcp import McpToolChat
from casual_mcp.tool_cache import ToolCache

# Setup
tool_cache = ToolCache(mcp_client)
chat = McpToolChat(mcp_client, llm_model, system_prompt, tool_cache=tool_cache)

# Simple prompt-based interface
response = await chat.generate("What time is it in London?")

# With session (for testing/dev only)
response = await chat.generate("What time is it?", session_id="my-session")

# Full message control
messages = [
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="What time is it in London?")
]
response = await chat.chat(messages)
```

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

After calling `chat()` or `generate()`, retrieve usage statistics via `get_stats()`:

```python
response = await chat.chat(messages)
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

Stats reset at the start of each `chat()` or `generate()` call.

## Response Structure

`chat()` and `generate()` return a list of `ChatMessage` objects:

```python
response_messages = await chat.chat(messages)
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
response = await chat.chat(messages, tool_set=toolset)

# Use with generate()
response = await chat.generate("What time is it?", tool_set=toolset)
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

### Tool Result Formatting

Control how results are presented to the LLM:

```bash
export TOOL_RESULT_FORMAT=result              # Raw result
export TOOL_RESULT_FORMAT=function_result     # "get_weather → 72°F"
export TOOL_RESULT_FORMAT=function_args_result # "get_weather(location='London') → 15°C"
```

### Session Management

> **Note**: Sessions are for testing/development only. In production, manage your own message history.

```python
# Development/testing with sessions
response = await chat.generate("What's the weather?", session_id="test-123")
response = await chat.generate("How about tomorrow?", session_id="test-123")

# Production: manage your own history
messages = []
messages.append(UserMessage(content="What's the weather?"))
response_msgs = await chat.chat(messages)
messages.extend(response_msgs)

messages.append(UserMessage(content="How about tomorrow?"))
response_msgs = await chat.chat(messages)
```

### Tool Cache

Tools are cached for 30 seconds by default. Configure with `MCP_TOOL_CACHE_TTL`:

```bash
export MCP_TOOL_CACHE_TTL=0   # Cache indefinitely
export MCP_TOOL_CACHE_TTL=5   # 5-second refresh
```
