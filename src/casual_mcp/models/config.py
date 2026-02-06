from pydantic import BaseModel, Field

from casual_mcp.models.mcp_server_config import McpServerConfig
from casual_mcp.models.model_config import McpModelConfig
from casual_mcp.models.toolset_config import ToolSetConfig


class Config(BaseModel):
    namespace_tools: bool | None = False
    models: dict[str, McpModelConfig]
    servers: dict[str, McpServerConfig]
    tool_sets: dict[str, ToolSetConfig] = Field(default_factory=dict)
