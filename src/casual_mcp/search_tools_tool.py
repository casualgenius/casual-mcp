"""Manifest generation and SearchToolsTool for LLM-driven tool discovery.

This module provides:
- ``generate_manifest``: Builds a compressed text manifest describing deferred
  tools grouped by server, suitable for embedding in a tool description.
- ``SearchToolsTool``: A ``SyntheticTool`` implementation that lets the LLM
  discover and load deferred tools via keyword search, server browsing, or
  exact name lookup.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import mcp
from casual_llm import Tool

from casual_mcp.logging import get_logger
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.synthetic_tool import SyntheticToolResult
from casual_mcp.tool_search_index import ToolSearchIndex

logger = get_logger("search_tools_tool")

# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

_MAX_TOOL_NAMES_SHOWN = 4
_MAX_DESCRIPTION_LENGTH = 80


def _first_sentence(text: str) -> str:
    """Extract the first sentence from *text*.

    Splits on ``". "`` or ``"."`` at the end so that abbreviations inside
    sentences are less likely to cause a premature split.
    """
    text = text.strip()
    dot_pos = text.find(". ")
    if dot_pos != -1:
        return text[: dot_pos + 1]
    if text.endswith("."):
        return text
    # No sentence-ending period found -- return the whole string.
    return text


def _summarise_server(tools: Sequence[mcp.Tool]) -> str:
    """Build a short summary description for a server from its tools."""
    seen: list[str] = []
    for tool in tools:
        desc = tool.description or ""
        sentence = _first_sentence(desc)
        if sentence and sentence not in seen:
            seen.append(sentence)
    summary = " ".join(seen)
    if len(summary) > _MAX_DESCRIPTION_LENGTH:
        summary = summary[: _MAX_DESCRIPTION_LENGTH - 3].rstrip() + "..."
    return summary


def generate_manifest(
    deferred_by_server: Mapping[str, Sequence[mcp.Tool]],
) -> str:
    """Produce a compressed text manifest of deferred tools grouped by server.

    The manifest is intended to be embedded inside the ``search-tools`` tool
    description so the LLM knows what is available for discovery.

    Format per server::

        - {server} ({n} tools): {tool_names}
          {summary_description}

    For servers with more than 10 tools the tool names are truncated to the
    first four names followed by ``... and N more``.

    Args:
        deferred_by_server: Mapping of server name to the MCP tools that are
            deferred (not yet loaded) on that server.

    Returns:
        Multi-line text manifest string.
    """
    lines: list[str] = []
    for server_name in sorted(deferred_by_server):
        tools = deferred_by_server[server_name]
        count = len(tools)
        tool_names = [t.name for t in tools]

        if count > 10:
            shown = ", ".join(tool_names[:_MAX_TOOL_NAMES_SHOWN])
            remaining = count - _MAX_TOOL_NAMES_SHOWN
            names_str = f"{shown}, ... and {remaining} more"
        else:
            names_str = ", ".join(tool_names)

        summary = _summarise_server(tools)
        tool_word = "tool" if count == 1 else "tools"
        lines.append(f"- {server_name} ({count} {tool_word}): {names_str}")
        if summary:
            lines.append(f"  {summary}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool result formatting helpers
# ---------------------------------------------------------------------------


def _format_param_details(input_schema: dict[str, Any]) -> str:
    """Format parameter details from an MCP tool's inputSchema."""
    props = input_schema.get("properties", {})
    required_names: set[str] = set(input_schema.get("required", []))
    if not props:
        return "  No parameters."

    parts: list[str] = []
    for pname, pdef in props.items():
        ptype = pdef.get("type", "any")
        req_marker = " (required)" if pname in required_names else ""
        pdesc = pdef.get("description", "")
        desc_part = f" - {pdesc}" if pdesc else ""
        parts.append(f"    - {pname}: {ptype}{req_marker}{desc_part}")
    return "\n".join(parts)


def _format_tool_details(server_name: str, tool: mcp.Tool) -> str:
    """Format a single tool's details for the search result text."""
    desc = tool.description or "(no description)"
    header = f"  [{server_name}] {tool.name}: {desc}"
    params = _format_param_details(tool.inputSchema)
    return f"{header}\n  Parameters:\n{params}"


# ---------------------------------------------------------------------------
# SearchToolsTool
# ---------------------------------------------------------------------------


class SearchToolsTool:
    """Synthetic tool that enables LLM-driven discovery of deferred tools.

    The tool is presented to the LLM with a manifest of all deferred servers
    and their tools embedded in its description. The LLM can then invoke it
    with a keyword ``query``, a ``server_name``, exact ``tool_names``, or
    combinations thereof.

    When tools are found, they are moved from the internal *deferred* set to
    the *loaded* set and returned in ``SyntheticToolResult.newly_loaded_tools``
    so that the chat loop can inject them into subsequent model calls.

    Args:
        deferred_tools: Mapping of server name to deferred MCP tools.
        server_names: Sequence of valid server names (used for validation).
        search_index: A ``ToolSearchIndex`` built over the deferred tools.
        config: ``ToolDiscoveryConfig`` providing ``max_search_results``.
    """

    _TOOL_NAME = "search-tools"

    def __init__(
        self,
        deferred_tools: Mapping[str, Sequence[mcp.Tool]],
        server_names: Sequence[str],
        search_index: ToolSearchIndex,
        config: ToolDiscoveryConfig,
    ) -> None:
        self._search_index = search_index
        self._config = config
        self._server_names: list[str] = list(server_names)

        # Build deferred/loaded tracking sets from the input mapping
        self._deferred_tools: set[str] = set()
        self._loaded_tools: set[str] = set()
        self._tool_lookup: dict[str, mcp.Tool] = {}
        self._deferred_by_server: dict[str, list[mcp.Tool]] = {}

        for server, tools in deferred_tools.items():
            tool_list: list[mcp.Tool] = list(tools)
            self._deferred_by_server[server] = tool_list
            for tool in tool_list:
                self._deferred_tools.add(tool.name)
                self._tool_lookup[tool.name] = tool

        self._manifest = generate_manifest(self._deferred_by_server)

    # -- SyntheticTool protocol ------------------------------------------------

    @property
    def name(self) -> str:
        """Unique name for this synthetic tool."""
        return self._TOOL_NAME

    @property
    def definition(self) -> Tool:
        """The casual-llm Tool definition sent to the LLM.

        The description includes the full manifest of deferred servers/tools
        so the LLM can formulate appropriate search queries.
        """
        description = (
            "Search for and load additional tools that are available but not yet loaded.\n"
            "Use this tool to discover tools you need to complete a task.\n"
            "\n"
            "Available tool servers:\n"
            f"{self._manifest}\n"
            "\n"
            "Provide at least one of: query, server_name, or tool_names."
        )
        return Tool.from_input_schema(
            name=self._TOOL_NAME,
            description=description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Keyword search query to find relevant tools" " by name or description."
                        ),
                    },
                    "server_name": {
                        "type": "string",
                        "description": (
                            "Load all tools from a specific server. "
                            f"Valid servers: {', '.join(sorted(self._server_names))}."
                        ),
                    },
                    "tool_names": {
                        "type": "array",
                        "description": "Exact tool names to load.",
                        "items": {"type": "string"},
                    },
                },
                "required": [],
            },
        )

    async def execute(self, args: dict[str, Any]) -> SyntheticToolResult:
        """Execute the search-tools tool with the given arguments.

        Supports the following parameter combinations:

        - ``query`` only: BM25 keyword search across all deferred tools.
        - ``server_name`` only: Load all tools from the named server.
        - ``tool_names`` only: Exact lookup by tool name.
        - ``server_name + query``: Scoped keyword search within a server.
        - ``server_name + tool_names``: Exact lookup filtered to a server.
        - ``query + tool_names``: ``tool_names`` takes precedence.

        Returns:
            ``SyntheticToolResult`` with human-readable result text and
            ``newly_loaded_tools`` containing only tools not previously loaded.
        """
        query: str | None = args.get("query")
        server_name: str | None = args.get("server_name")
        tool_names: list[str] | None = args.get("tool_names")

        # Normalise empty strings / empty lists to None
        if query is not None and not query.strip():
            query = None
        if tool_names is not None and len(tool_names) == 0:
            tool_names = None

        # --- No parameters provided ---
        if query is None and server_name is None and tool_names is None:
            return SyntheticToolResult(
                content="Error: Please provide at least one of: query, server_name, or tool_names.",
                newly_loaded_tools=[],
            )

        # --- Validate server_name ---
        if server_name is not None and server_name not in self._server_names:
            valid = ", ".join(sorted(self._server_names))
            return SyntheticToolResult(
                content=(f"Error: Unknown server '{server_name}'. " f"Valid servers: {valid}."),
                newly_loaded_tools=[],
            )

        # --- Resolve results depending on parameter combination ---
        results: list[tuple[str, mcp.Tool]]

        if tool_names is not None:
            # tool_names takes precedence when combined with query
            found, not_found = self._search_index.get_by_names(tool_names)
            # If server_name is given, filter to that server
            if server_name is not None:
                found = [(s, t) for s, t in found if s == server_name]
            results = found
            if not_found:
                not_found_msg = f"Not found: {', '.join(not_found)}."
            else:
                not_found_msg = ""
        elif server_name is not None and query is not None:
            # Scoped search within a server
            results = self._search_index.search(
                query,
                max_results=self._config.max_search_results,
                server_filter=server_name,
            )
            not_found_msg = ""
        elif server_name is not None:
            # Load all tools from server
            results = self._search_index.get_by_server(server_name)
            not_found_msg = ""
        else:
            # query-only BM25 search
            assert query is not None
            results = self._search_index.search(
                query,
                max_results=self._config.max_search_results,
            )
            not_found_msg = ""

        # --- No results ---
        if not results:
            parts = ["No tools found"]
            if query:
                parts.append(f"matching '{query}'")
            if server_name:
                parts.append(f"in server '{server_name}'")
            msg = " ".join(parts) + "."
            if not_found_msg:
                msg += f" {not_found_msg}"
            return SyntheticToolResult(content=msg, newly_loaded_tools=[])

        # --- Partition into newly-loaded vs already-loaded ---
        newly_loaded: list[mcp.Tool] = []
        already_loaded: list[str] = []
        details_parts: list[str] = []

        for sname, tool in results:
            if tool.name in self._loaded_tools:
                already_loaded.append(tool.name)
            else:
                newly_loaded.append(tool)
                self._deferred_tools.discard(tool.name)
                self._loaded_tools.add(tool.name)
            details_parts.append(_format_tool_details(sname, tool))

        # --- Build result text ---
        text_parts: list[str] = []
        text_parts.append(f"Found {len(results)} tool(s):\n")
        text_parts.append("\n\n".join(details_parts))

        if already_loaded:
            text_parts.append(f"\n\nAlready loaded: {', '.join(already_loaded)}")

        if not_found_msg:
            text_parts.append(f"\n\n{not_found_msg}")

        content = "".join(text_parts)

        logger.debug(
            f"search-tools: {len(newly_loaded)} newly loaded, "
            f"{len(already_loaded)} already loaded"
        )

        return SyntheticToolResult(
            content=content,
            newly_loaded_tools=newly_loaded,
        )
