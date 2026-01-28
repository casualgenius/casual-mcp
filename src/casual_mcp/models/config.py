from pydantic import BaseModel

from casual_mcp.models.mcp_server_config import McpServerConfig
from casual_mcp.models.model_config import McpModelConfig


class Config(BaseModel):
    namespace_tools: bool | None = False
    models: dict[str, McpModelConfig]
    servers: dict[str, McpServerConfig]
