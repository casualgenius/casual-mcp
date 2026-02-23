from typing import Any, Literal

from pydantic import BaseModel, Field


class StdioServerConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, Any] = Field(default_factory=dict)
    cwd: str | None = None
    transport: Literal["stdio"] = "stdio"
    defer_loading: bool = False


class RemoteServerConfig(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    transport: Literal["streamable-http", "sse", "http"] | None = None
    defer_loading: bool = False


McpServerConfig = StdioServerConfig | RemoteServerConfig
