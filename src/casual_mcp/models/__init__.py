from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    ChatMessage,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)

from .chat_stats import (
    ChatStats,
    TokenUsageStats,
    ToolCallStats,
)
from .config import McpClientConfig, McpModelConfig
from .mcp_server_config import (
    McpServerConfig,
    RemoteServerConfig,
    StdioServerConfig,
)
from .toolset_config import (
    ExcludeSpec,
    ToolSetConfig,
    ToolSpec,
)

# Deprecated aliases for backwards compatibility
OpenAIModelConfig = McpModelConfig
OllamaModelConfig = McpModelConfig

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "AssistantToolCall",
    "ToolResultMessage",
    "SystemMessage",
    "ChatMessage",
    "ChatStats",
    "TokenUsageStats",
    "ToolCallStats",
    "McpClientConfig",
    "McpModelConfig",
    "OpenAIModelConfig",
    "OllamaModelConfig",
    "McpServerConfig",
    "StdioServerConfig",
    "RemoteServerConfig",
    "ExcludeSpec",
    "ToolSetConfig",
    "ToolSpec",
]
