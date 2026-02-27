"""Tool discovery configuration model."""

from pydantic import BaseModel, Field


class ToolDiscoveryConfig(BaseModel):
    """Configuration for the tool discovery system.

    When enabled, tools from servers marked with defer_loading=True are not
    loaded eagerly. Instead, a synthetic 'search-tools' tool is injected
    that allows the LLM to discover and load deferred tools on demand via
    BM25 keyword search.

    Attributes:
        enabled: Whether tool discovery is active. When False, all servers
            load tools eagerly as normal.
        defer_all: When True, all servers are treated as deferred regardless
            of their individual defer_loading setting.
        max_search_results: Maximum number of tools returned by a single
            search query.
    """

    enabled: bool = Field(
        default=False,
        description="Whether tool discovery is active",
    )
    defer_all: bool = Field(
        default=False,
        description="Treat all servers as deferred regardless of per-server setting",
    )
    max_search_results: int = Field(
        default=5,
        ge=1,
        description="Maximum number of tools returned by a single search query",
    )
