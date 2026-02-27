"""Orchestration module for tool discovery in the McpToolChat loop.

Provides helpers for partitioning MCP tools into loaded (eager) and deferred
sets based on server configuration and tool discovery settings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import mcp

from casual_mcp.logging import get_logger
from casual_mcp.models.config import Config
from casual_mcp.models.mcp_server_config import McpServerConfig
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.tool_filter import extract_server_and_tool

logger = get_logger("tool_discovery")


def partition_tools(
    tools: Sequence[mcp.Tool],
    config: Config,
    server_names: set[str],
) -> tuple[list[mcp.Tool], dict[str, list[mcp.Tool]]]:
    """Partition tools into loaded (eager) and deferred sets.

    Uses the ``ToolDiscoveryConfig`` and per-server ``defer_loading`` flags
    to determine which tools should be immediately available and which
    should be deferred for on-demand discovery.

    Args:
        tools: All available MCP tools (already filtered by toolset if applicable).
        config: The full application config containing server definitions and
            tool discovery settings.
        server_names: Set of known server names for tool name parsing.

    Returns:
        A tuple of ``(loaded_tools, deferred_by_server)`` where:
        - ``loaded_tools`` is the list of tools to send to the LLM immediately.
        - ``deferred_by_server`` maps server name to the deferred tools from
          that server. Empty dict if no tools are deferred.
    """
    discovery = config.tool_discovery
    if discovery is None or not discovery.enabled:
        return list(tools), {}

    # Build a lookup from server name to its config for defer_loading checks
    server_configs: Mapping[str, McpServerConfig] = config.servers

    loaded: list[mcp.Tool] = []
    deferred_by_server: dict[str, list[mcp.Tool]] = {}

    for tool in tools:
        server_name, _ = extract_server_and_tool(tool.name, server_names)
        should_defer = _should_defer_tool(server_name, server_configs, discovery)

        if should_defer:
            deferred_by_server.setdefault(server_name, []).append(tool)
        else:
            loaded.append(tool)

    if deferred_by_server:
        total_deferred = sum(len(t) for t in deferred_by_server.values())
        logger.info(
            f"Partitioned tools: {len(loaded)} loaded, "
            f"{total_deferred} deferred across {len(deferred_by_server)} servers"
        )
    else:
        logger.debug("No deferred tools - all tools loaded eagerly")

    return loaded, deferred_by_server


def _should_defer_tool(
    server_name: str,
    server_configs: Mapping[str, McpServerConfig],
    discovery: ToolDiscoveryConfig,
) -> bool:
    """Determine whether tools from a given server should be deferred.

    Args:
        server_name: The server the tool belongs to.
        server_configs: Mapping of server name to config.
        discovery: The tool discovery configuration.

    Returns:
        True if the tool should be deferred, False if it should be loaded eagerly.
    """
    if discovery.defer_all:
        return True

    server_cfg = server_configs.get(server_name)
    if server_cfg is None:
        # Unknown server -- load eagerly to be safe
        return False

    return server_cfg.defer_loading


def build_tool_server_map(
    tools: Sequence[mcp.Tool],
    server_names: set[str],
) -> dict[str, str]:
    """Build a mapping of tool name to server name.

    Args:
        tools: MCP tools to map.
        server_names: Known server names for prefix extraction.

    Returns:
        Dict mapping tool name to its server name.
    """
    mapping: dict[str, str] = {}
    for tool in tools:
        server_name, _ = extract_server_and_tool(tool.name, server_names)
        mapping[tool.name] = server_name
    return mapping
