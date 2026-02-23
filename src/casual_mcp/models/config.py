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
    namespace_tools: bool | None = False
    clients: dict[str, McpClientConfig] = Field(default_factory=dict)
    models: dict[str, McpModelConfig]
    servers: dict[str, McpServerConfig]
    tool_sets: dict[str, ToolSetConfig] = Field(default_factory=dict)
    tool_discovery: ToolDiscoveryConfig | None = None
