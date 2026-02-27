"""SyntheticTool protocol for tools handled internally by casual-mcp.

Synthetic tools are intercepted in the McpToolChat loop and executed locally
rather than being forwarded to MCP servers. This enables features like tool
discovery (search-tools) that operate on internal state.
"""

from typing import Any, NamedTuple, Protocol

import mcp
from casual_llm import Tool


class SyntheticToolResult(NamedTuple):
    """Result from executing a synthetic tool.

    Attributes:
        content: The text content to return to the LLM.
        newly_loaded_tools: MCP tools to add to the loaded tool set.
            Used by the chat loop for dynamic tool expansion (e.g.,
            loading tools found via search-tools).
    """

    content: str
    newly_loaded_tools: list[mcp.Tool]


class SyntheticTool(Protocol):
    """Protocol for tools handled internally by casual-mcp.

    Synthetic tools provide their own casual-llm Tool definition and
    are executed directly in the McpToolChat loop instead of being
    dispatched to an MCP server.

    Implementations must provide:
        - name: Unique tool name (used for registry lookup)
        - definition: casual-llm Tool instance (sent to the LLM)
        - execute: Async method that processes arguments and returns results
    """

    @property
    def name(self) -> str:
        """Unique name for this synthetic tool."""
        ...

    @property
    def definition(self) -> Tool:
        """The casual-llm Tool definition sent to the LLM."""
        ...

    async def execute(self, args: dict[str, Any]) -> SyntheticToolResult:
        """Execute the synthetic tool with the given arguments.

        Args:
            args: Tool arguments parsed from the LLM's tool call.

        Returns:
            SyntheticToolResult with content and any newly loaded tools.
        """
        ...
