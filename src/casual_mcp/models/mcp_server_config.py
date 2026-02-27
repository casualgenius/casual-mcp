"""MCP server configuration models.

Defines configuration for stdio-based and remote (HTTP/SSE) MCP servers.
Each server config supports a ``defer_loading`` flag used by the tool
discovery system to defer tool loading until the LLM requests them.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class StdioServerConfig(BaseModel):
    """Configuration for a stdio-based MCP server.

    Attributes:
        command: The command to run (e.g. ``"python"``).
        args: Command-line arguments passed to the server process.
        env: Environment variables set for the server process.
        cwd: Working directory for the server process.
        transport: Always ``"stdio"`` for this server type.
        defer_loading: When True and tool discovery is enabled, tools
            from this server are deferred and discoverable via search-tools.
    """

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, Any] = Field(default_factory=dict)
    cwd: str | None = None
    transport: Literal["stdio"] = "stdio"
    defer_loading: bool = False


class RemoteServerConfig(BaseModel):
    """Configuration for a remote MCP server accessed over HTTP or SSE.

    Attributes:
        url: The server URL.
        headers: HTTP headers sent with requests to the server.
        transport: Transport protocol (``"streamable-http"``, ``"sse"``,
            or ``"http"``). Auto-detected if not specified.
        defer_loading: When True and tool discovery is enabled, tools
            from this server are deferred and discoverable via search-tools.
    """

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    transport: Literal["streamable-http", "sse", "http"] | None = None
    defer_loading: bool = False


McpServerConfig = StdioServerConfig | RemoteServerConfig
