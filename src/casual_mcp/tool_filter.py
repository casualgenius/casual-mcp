"""Tool filtering logic for toolsets.

This module provides functionality to filter MCP tools based on toolset
configurations, including validation to ensure referenced servers and
tools actually exist.
"""

import mcp

from casual_mcp.logging import get_logger
from casual_mcp.models.toolset_config import ExcludeSpec, ToolSetConfig

logger = get_logger("tool_filter")


class ToolSetValidationError(Exception):
    """Raised when a toolset references invalid servers or tools."""

    pass


def extract_server_and_tool(tool_name: str, server_names: set[str]) -> tuple[str, str]:
    """Extract server name and base tool name from a potentially prefixed tool name.

    When multiple servers are configured, fastmcp prefixes tools as "serverName_toolName".
    When a single server is configured, tools are not prefixed.

    Args:
        tool_name: The full tool name (possibly prefixed)
        server_names: Set of configured server names

    Returns:
        Tuple of (server_name, base_tool_name)
    """
    if "_" in tool_name:
        prefix = tool_name.split("_", 1)[0]
        if prefix in server_names:
            return prefix, tool_name.split("_", 1)[1]

    # Single server case - return the single server name
    if len(server_names) == 1:
        return next(iter(server_names)), tool_name

    # Fallback - can't determine server
    return "default", tool_name


def _build_server_tool_map(tools: list[mcp.Tool], server_names: set[str]) -> dict[str, set[str]]:
    """Build a mapping of server names to their available tool names.

    Args:
        tools: List of MCP tools
        server_names: Set of configured server names

    Returns:
        Dict mapping server name to set of base tool names
    """
    server_tool_map: dict[str, set[str]] = {name: set() for name in server_names}

    for tool in tools:
        server_name, base_name = extract_server_and_tool(tool.name, server_names)
        if server_name in server_tool_map:
            server_tool_map[server_name].add(base_name)

    return server_tool_map


def validate_toolset(
    toolset: ToolSetConfig,
    tools: list[mcp.Tool],
    server_names: set[str],
) -> None:
    """Validate that a toolset references only valid servers and tools.

    Args:
        toolset: The toolset configuration to validate
        tools: List of available MCP tools
        server_names: Set of configured server names

    Raises:
        ToolSetValidationError: If the toolset references non-existent servers or tools
    """
    server_tool_map = _build_server_tool_map(tools, server_names)
    errors: list[str] = []

    for server_name, tool_spec in toolset.servers.items():
        # Check server exists
        if server_name not in server_names:
            errors.append(f"Server '{server_name}' not found in configuration")
            continue

        available = server_tool_map.get(server_name, set())

        # Validate tool names in include list
        if isinstance(tool_spec, list):
            for tool_name in tool_spec:
                if tool_name not in available:
                    errors.append(
                        f"Tool '{tool_name}' not found in server '{server_name}'. "
                        f"Available: {sorted(available)}"
                    )

        # Validate tool names in exclude list
        elif isinstance(tool_spec, ExcludeSpec):
            for tool_name in tool_spec.exclude:
                if tool_name not in available:
                    errors.append(
                        f"Tool '{tool_name}' not found in server '{server_name}' "
                        f"(specified in exclude list). Available: {sorted(available)}"
                    )

    if errors:
        raise ToolSetValidationError("\n".join(errors))


def filter_tools_by_toolset(
    tools: list[mcp.Tool],
    toolset: ToolSetConfig,
    server_names: set[str],
    validate: bool = True,
) -> list[mcp.Tool]:
    """Filter a list of MCP tools based on a toolset configuration.

    Args:
        tools: Full list of available MCP tools
        toolset: The toolset configuration to apply
        server_names: Set of configured server names
        validate: Whether to validate the toolset first (raises on invalid)

    Returns:
        Filtered list of tools matching the toolset

    Raises:
        ToolSetValidationError: If validate=True and toolset is invalid
    """
    if validate:
        validate_toolset(toolset, tools, server_names)

    filtered: list[mcp.Tool] = []

    for tool in tools:
        server_name, base_name = extract_server_and_tool(tool.name, server_names)

        # Check if this server is in the toolset
        if server_name not in toolset.servers:
            continue

        tool_spec = toolset.servers[server_name]

        # Determine if tool should be included
        include = False

        if tool_spec is True:
            # All tools from this server
            include = True
        elif isinstance(tool_spec, list):
            # Only specific tools
            include = base_name in tool_spec
        elif isinstance(tool_spec, ExcludeSpec):
            # All except excluded tools
            include = base_name not in tool_spec.exclude

        if include:
            filtered.append(tool)

    logger.debug(
        f"Filtered {len(tools)} tools to {len(filtered)} using toolset "
        f"with {len(toolset.servers)} servers"
    )

    return filtered
