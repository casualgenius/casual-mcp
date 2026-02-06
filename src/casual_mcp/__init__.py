from importlib.metadata import version

from . import models
from .models.chat_stats import ChatStats, TokenUsageStats, ToolCallStats

__version__ = version("casual-mcp")
from .mcp_tool_chat import McpToolChat
from .model_factory import ModelFactory
from .tool_cache import ToolCache
from .utils import load_config, load_mcp_client, render_system_prompt

__all__ = [
    "__version__",
    "McpToolChat",
    "ModelFactory",
    "ToolCache",
    "load_config",
    "load_mcp_client",
    "render_system_prompt",
    "models",
    "ChatStats",
    "TokenUsageStats",
    "ToolCallStats",
]
