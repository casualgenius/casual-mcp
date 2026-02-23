from pydantic import BaseModel, Field, SecretStr

from casual_mcp.models.mcp_server_config import McpServerConfig
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.models.toolset_config import ToolSetConfig


class McpClientConfig(BaseModel):
    """Configuration for an LLM API client connection.

    Maps to casual-llm's ClientConfig.
    """

    provider: str
    base_url: str | None = None
    api_key: SecretStr | None = None
    timeout: float = 60.0


class McpModelConfig(BaseModel):
    """Configuration for an LLM model.

    References a named client and specifies model-specific settings.
    Maps to casual-llm's ModelConfig.
    """

    client: str
    model: str
    template: str | None = None
    temperature: float | None = None


class Config(BaseModel):
    """Top-level application configuration loaded from ``casual_mcp_config.json``.

    Attributes:
        namespace_tools: Whether to prefix tool names with the server name.
        clients: Named LLM API client configurations.
        models: Named LLM model configurations (each references a client).
        servers: Named MCP server configurations (stdio or remote).
        tool_sets: Named toolset configurations for filtering available tools.
        tool_discovery: Optional tool discovery configuration. When present
            and enabled, tools from deferred servers are loaded on demand.
    """

    namespace_tools: bool | None = False
    clients: dict[str, McpClientConfig] = Field(default_factory=dict)
    models: dict[str, McpModelConfig]
    servers: dict[str, McpServerConfig]
    tool_sets: dict[str, ToolSetConfig] = Field(default_factory=dict)
    tool_discovery: ToolDiscoveryConfig | None = None
