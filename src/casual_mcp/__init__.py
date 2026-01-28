from importlib.metadata import version

from . import models

__version__ = version("casual-mcp")
from .mcp_tool_chat import McpToolChat
from .provider_factory import ProviderFactory
from .tool_cache import ToolCache
from .utils import load_config, load_mcp_client, render_system_prompt

__all__ = [
    "__version__",
    "McpToolChat",
    "ProviderFactory",
    "ToolCache",
    "load_config",
    "load_mcp_client",
    "render_system_prompt",
    "models",
]
