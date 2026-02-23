"""BM25-based search index for MCP tools.

This module provides a search index that enables keyword-based discovery of MCP
tools using BM25 (Okapi) ranking. Tools are indexed by their name and description,
and can be queried by free-text search, server name, or exact tool name.
"""

import re
from collections.abc import Mapping, Sequence

import mcp
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from casual_mcp.logging import get_logger

logger = get_logger("tool_search_index")

_SPLIT_RE = re.compile(r"[\s_]+")


def _tokenize(text: str) -> list[str]:
    """Tokenize text by lowercasing and splitting on whitespace and underscores.

    Tool names often use underscores as word separators (e.g.
    ``search_brave_web_search``), so splitting on both whitespace and
    underscores produces more useful tokens for BM25 matching.
    """
    return [tok for tok in _SPLIT_RE.split(text.lower()) if tok]


class ToolSearchIndex:
    """BM25-based search index over MCP tools.

    Builds a BM25Okapi index from tool names and descriptions, supporting
    ranked keyword search, server-based filtering, and exact name lookup.

    Args:
        tools: MCP tools to index.
        tool_server_map: Mapping of full tool name to its server name.
    """

    def __init__(
        self,
        tools: Sequence[mcp.Tool],
        tool_server_map: Mapping[str, str],
    ) -> None:
        self._tools: list[mcp.Tool] = list(tools)
        self._tool_server_map: dict[str, str] = dict(tool_server_map)

        # Build name-based lookup for get_by_names
        self._tools_by_name: dict[str, mcp.Tool] = {t.name: t for t in self._tools}

        # Build server-based lookup for get_by_server
        self._tools_by_server: dict[str, list[mcp.Tool]] = {}
        for tool in self._tools:
            server = self._tool_server_map.get(tool.name, "unknown")
            self._tools_by_server.setdefault(server, []).append(tool)

        # Build BM25 corpus and store tokenized docs for fallback
        self._corpus: list[list[str]] = []
        for tool in self._tools:
            doc_text = f"{tool.name} {tool.description or ''}"
            self._corpus.append(_tokenize(doc_text))

        # BM25Okapi requires at least one document; handle empty gracefully
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

        logger.debug(
            f"Built search index with {len(self._tools)} tools "
            f"across {len(self._tools_by_server)} servers"
        )

    def search(
        self,
        query: str,
        max_results: int = 5,
        server_filter: str | None = None,
    ) -> list[tuple[str, mcp.Tool]]:
        """Search for tools matching a query, ranked by BM25 relevance.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to return.
            server_filter: If provided, only return tools from this server.

        Returns:
            List of (server_name, tool) tuples ranked by relevance score.
            Only results with BM25 score > 0 are included.
        """
        if self._bm25 is None or not query.strip():
            return []

        tokenized_query = _tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Pair each tool with its score and filter to score > 0
        scored: list[tuple[float, mcp.Tool]] = []
        for i, tool in enumerate(self._tools):
            score = float(scores[i])
            if score > 0:
                scored.append((score, tool))

        # BM25Okapi assigns IDF=0 when a term appears in all documents (common
        # with very small corpora). Fall back to simple token overlap counting
        # so that single-tool indexes and other degenerate cases still return
        # matches.
        if not scored:
            query_tokens = set(tokenized_query)
            for i, tool in enumerate(self._tools):
                overlap = len(query_tokens & set(self._corpus[i]))
                if overlap > 0:
                    scored.append((float(overlap), tool))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Build results, applying server filter after scoring
        results: list[tuple[str, mcp.Tool]] = []
        for _score, tool in scored:
            server_name = self._tool_server_map.get(tool.name, "unknown")
            if server_filter is not None and server_name != server_filter:
                continue
            results.append((server_name, tool))
            if len(results) >= max_results:
                break

        return results

    def get_by_server(self, server_name: str) -> list[tuple[str, mcp.Tool]]:
        """Return all tools belonging to a specific server.

        Args:
            server_name: The server name to filter by.

        Returns:
            List of (server_name, tool) tuples for the given server.
        """
        tools = self._tools_by_server.get(server_name, [])
        return [(server_name, tool) for tool in tools]

    def get_by_names(
        self,
        tool_names: Sequence[str],
    ) -> tuple[list[tuple[str, mcp.Tool]], list[str]]:
        """Look up tools by exact name.

        Args:
            tool_names: Sequence of tool names to look up.

        Returns:
            A tuple of (found, not_found) where:
            - found is a list of (server_name, tool) tuples for matched names
            - not_found is a list of tool names that did not match
        """
        found: list[tuple[str, mcp.Tool]] = []
        not_found: list[str] = []

        for name in tool_names:
            tool = self._tools_by_name.get(name)
            if tool is not None:
                server_name = self._tool_server_map.get(name, "unknown")
                found.append((server_name, tool))
            else:
                not_found.append(name)

        return found, not_found

    @property
    def tool_count(self) -> int:
        """Return the total number of indexed tools."""
        return len(self._tools)

    @property
    def server_names(self) -> list[str]:
        """Return the list of server names with indexed tools."""
        return list(self._tools_by_server.keys())
