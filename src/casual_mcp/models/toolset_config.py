"""Toolset configuration models for filtering available tools."""

from pydantic import BaseModel, Field


class ExcludeSpec(BaseModel):
    """Specification for excluding specific tools from a server."""

    exclude: list[str] = Field(description="List of tool names to exclude")


# Tool specification: true (all), list (include specific), or exclude object
ToolSpec = bool | list[str] | ExcludeSpec


class ToolSetConfig(BaseModel):
    """Configuration for a named toolset.

    A toolset defines which tools from which servers should be available
    during a chat session. Each server can be configured to:
    - Include all tools (True)
    - Include specific tools (list of tool names)
    - Include all except specific tools (ExcludeSpec)

    Example:
        {
            "description": "Research tools",
            "servers": {
                "wikimedia": True,
                "search": ["brave_web_search"],
                "fetch": {"exclude": ["fetch_dangerous"]}
            }
        }
    """

    description: str = Field(default="", description="Human-readable description")
    servers: dict[str, ToolSpec] = Field(
        default_factory=dict,
        description="Mapping of server name to tool specification",
    )
