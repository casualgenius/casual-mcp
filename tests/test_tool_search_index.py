"""Tests for ToolSearchIndex BM25-based tool search."""

import mcp
import pytest

from casual_mcp.tool_search_index import ToolSearchIndex, _tokenize


def _make_tool(name: str, description: str) -> mcp.Tool:
    """Helper to create an mcp.Tool with minimal required fields."""
    return mcp.Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": {}},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_server_tools() -> list[mcp.Tool]:
    """A set of tools spread across multiple servers."""
    return [
        _make_tool("search_brave_web_search", "Search the web using Brave"),
        _make_tool("search_brave_local_search", "Search local results using Brave"),
        _make_tool("weather_get_forecast", "Get weather forecast for a location"),
        _make_tool("weather_get_current", "Get current weather conditions"),
        _make_tool("time_get_current_time", "Get the current time in a timezone"),
        _make_tool("math_add", "Add two numbers together"),
        _make_tool("math_multiply", "Multiply two numbers together"),
    ]


@pytest.fixture
def multi_server_map() -> dict[str, str]:
    """Tool name to server name mapping for multi_server_tools."""
    return {
        "search_brave_web_search": "search",
        "search_brave_local_search": "search",
        "weather_get_forecast": "weather",
        "weather_get_current": "weather",
        "time_get_current_time": "time",
        "math_add": "math",
        "math_multiply": "math",
    }


@pytest.fixture
def index(multi_server_tools: list[mcp.Tool], multi_server_map: dict[str, str]) -> ToolSearchIndex:
    """A ToolSearchIndex built from the multi-server tools."""
    return ToolSearchIndex(multi_server_tools, multi_server_map)


# ---------------------------------------------------------------------------
# Tokenizer tests
# ---------------------------------------------------------------------------


class TestTokenize:
    """Tests for the _tokenize helper."""

    def test_basic_tokenization(self) -> None:
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_lowercases(self) -> None:
        assert _tokenize("BrAvE Search") == ["brave", "search"]

    def test_empty_string(self) -> None:
        assert _tokenize("") == []

    def test_multiple_spaces(self) -> None:
        tokens = _tokenize("  search   web  ")
        assert tokens == ["search", "web"]

    def test_underscores_split(self) -> None:
        """Underscores in tool names should be treated as word separators."""
        assert _tokenize("search_brave_web") == ["search", "brave", "web"]

    def test_mixed_whitespace_and_underscores(self) -> None:
        tokens = _tokenize("search_brave web_search")
        assert tokens == ["search", "brave", "web", "search"]


# ---------------------------------------------------------------------------
# Constructor and properties
# ---------------------------------------------------------------------------


class TestToolSearchIndexInit:
    """Tests for ToolSearchIndex construction and properties."""

    def test_tool_count(self, index: ToolSearchIndex) -> None:
        assert index.tool_count == 7

    def test_server_names(self, index: ToolSearchIndex) -> None:
        names = sorted(index.server_names)
        assert names == ["math", "search", "time", "weather"]

    def test_empty_index(self) -> None:
        idx = ToolSearchIndex([], {})
        assert idx.tool_count == 0
        assert idx.server_names == []


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for the search() method."""

    def test_basic_search_returns_relevant_results(self, index: ToolSearchIndex) -> None:
        """Searching for 'weather' should return weather-related tools."""
        results = index.search("weather")
        assert len(results) > 0
        # All returned tools should be weather-related
        tool_names = [tool.name for _, tool in results]
        assert any("weather" in name for name in tool_names)

    def test_search_ranking_order(self, index: ToolSearchIndex) -> None:
        """Tools more relevant to the query should rank higher."""
        results = index.search("search web brave")
        assert len(results) >= 2
        # The web search tool should rank at or near the top since
        # it matches all three query terms
        top_tool = results[0][1]
        assert top_tool.name == "search_brave_web_search"

    def test_search_returns_server_names(self, index: ToolSearchIndex) -> None:
        """Each result should include the correct server name."""
        results = index.search("forecast")
        assert len(results) >= 1
        server_name, tool = results[0]
        assert server_name == "weather"
        assert tool.name == "weather_get_forecast"

    def test_search_max_results(self, index: ToolSearchIndex) -> None:
        """max_results should limit the number of returned results."""
        # A broad query that could match many tools
        results = index.search("search", max_results=2)
        assert len(results) <= 2

    def test_search_max_results_one(self, index: ToolSearchIndex) -> None:
        results = index.search("weather", max_results=1)
        assert len(results) == 1

    def test_search_server_filter(self, index: ToolSearchIndex) -> None:
        """server_filter should restrict results to a single server."""
        # 'search' appears in tool names/descriptions of search server
        results = index.search("search", server_filter="search")
        assert len(results) > 0
        for server_name, _ in results:
            assert server_name == "search"

    def test_search_server_filter_excludes_other_servers(self, index: ToolSearchIndex) -> None:
        """A query matching multiple servers should be filtered correctly."""
        # 'get' appears in weather and time tools
        all_results = index.search("get current", max_results=10)
        filtered = index.search("get current", max_results=10, server_filter="time")
        assert len(filtered) <= len(all_results)
        for server_name, _ in filtered:
            assert server_name == "time"

    def test_search_server_filter_no_matches(self, index: ToolSearchIndex) -> None:
        """Server filter with non-matching server should return empty."""
        results = index.search("weather", server_filter="nonexistent")
        assert results == []

    def test_search_no_results(self, index: ToolSearchIndex) -> None:
        """A query with no matching terms should return empty."""
        results = index.search("xyzzyplugh")
        assert results == []

    def test_search_only_positive_scores(self, index: ToolSearchIndex) -> None:
        """Only tools with BM25 score > 0 should be returned."""
        results = index.search("multiply numbers")
        # Every result should be genuinely relevant
        for _, tool in results:
            # At least one query term should appear in name or description
            text = f"{tool.name} {tool.description}".lower()
            assert "multiply" in text or "numbers" in text or "number" in text

    def test_search_empty_query(self, index: ToolSearchIndex) -> None:
        """An empty query should return no results."""
        assert index.search("") == []

    def test_search_whitespace_query(self, index: ToolSearchIndex) -> None:
        """A whitespace-only query should return no results."""
        assert index.search("   ") == []

    def test_search_empty_index(self) -> None:
        """Search on an empty index should return no results."""
        idx = ToolSearchIndex([], {})
        assert idx.search("weather") == []

    def test_search_case_insensitive(self, index: ToolSearchIndex) -> None:
        """Search should be case-insensitive."""
        results_lower = index.search("weather")
        results_upper = index.search("WEATHER")
        results_mixed = index.search("Weather")
        assert len(results_lower) == len(results_upper) == len(results_mixed)
        for (_, t1), (_, t2) in zip(results_lower, results_upper):
            assert t1.name == t2.name


# ---------------------------------------------------------------------------
# get_by_server tests
# ---------------------------------------------------------------------------


class TestGetByServer:
    """Tests for the get_by_server() method."""

    def test_returns_all_tools_for_server(self, index: ToolSearchIndex) -> None:
        results = index.get_by_server("search")
        assert len(results) == 2
        names = {tool.name for _, tool in results}
        assert names == {"search_brave_web_search", "search_brave_local_search"}

    def test_correct_server_name_in_results(self, index: ToolSearchIndex) -> None:
        results = index.get_by_server("weather")
        for server_name, _ in results:
            assert server_name == "weather"

    def test_single_tool_server(self, index: ToolSearchIndex) -> None:
        results = index.get_by_server("time")
        assert len(results) == 1
        assert results[0][1].name == "time_get_current_time"

    def test_unknown_server_returns_empty(self, index: ToolSearchIndex) -> None:
        results = index.get_by_server("nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# get_by_names tests
# ---------------------------------------------------------------------------


class TestGetByNames:
    """Tests for the get_by_names() method."""

    def test_all_names_found(self, index: ToolSearchIndex) -> None:
        found, not_found = index.get_by_names(
            ["search_brave_web_search", "math_add"]
        )
        assert len(found) == 2
        assert not_found == []
        names = {tool.name for _, tool in found}
        assert names == {"search_brave_web_search", "math_add"}

    def test_correct_server_names(self, index: ToolSearchIndex) -> None:
        found, _ = index.get_by_names(
            ["search_brave_web_search", "weather_get_forecast"]
        )
        server_map = {tool.name: server for server, tool in found}
        assert server_map["search_brave_web_search"] == "search"
        assert server_map["weather_get_forecast"] == "weather"

    def test_some_names_not_found(self, index: ToolSearchIndex) -> None:
        found, not_found = index.get_by_names(
            ["math_add", "nonexistent_tool", "also_missing"]
        )
        assert len(found) == 1
        assert found[0][1].name == "math_add"
        assert sorted(not_found) == ["also_missing", "nonexistent_tool"]

    def test_all_names_not_found(self, index: ToolSearchIndex) -> None:
        found, not_found = index.get_by_names(["nope", "not_here"])
        assert found == []
        assert sorted(not_found) == ["nope", "not_here"]

    def test_empty_names_list(self, index: ToolSearchIndex) -> None:
        found, not_found = index.get_by_names([])
        assert found == []
        assert not_found == []

    def test_duplicate_names(self, index: ToolSearchIndex) -> None:
        """Duplicate names in input should each be looked up."""
        found, not_found = index.get_by_names(["math_add", "math_add"])
        assert len(found) == 2
        assert not_found == []


# ---------------------------------------------------------------------------
# Edge case / integration tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_tool_without_description(self) -> None:
        """Tools with empty description should still be indexed by name."""
        tool = mcp.Tool(
            name="simple_tool",
            description="",
            inputSchema={"type": "object", "properties": {}},
        )
        idx = ToolSearchIndex([tool], {"simple_tool": "myserver"})
        results = idx.search("simple")
        assert len(results) == 1
        assert results[0][1].name == "simple_tool"

    def test_tool_with_none_description(self) -> None:
        """Tools with None description should still be indexed by name."""
        tool = mcp.Tool(
            name="simple_tool",
            description=None,
            inputSchema={"type": "object", "properties": {}},
        )
        idx = ToolSearchIndex([tool], {"simple_tool": "myserver"})
        results = idx.search("simple")
        assert len(results) == 1

    def test_single_tool_index(self) -> None:
        """An index with a single tool should work correctly."""
        tool = _make_tool("only_tool", "The one and only tool")
        idx = ToolSearchIndex([tool], {"only_tool": "solo"})
        assert idx.tool_count == 1
        results = idx.search("only tool")
        assert len(results) == 1
        assert results[0] == ("solo", tool)

    def test_missing_server_mapping_defaults_to_unknown(self) -> None:
        """Tools not in the server map should map to 'unknown'."""
        tool = _make_tool("orphan_tool", "An orphan tool")
        # Intentionally not providing a mapping for this tool
        idx = ToolSearchIndex([tool], {})
        results = idx.search("orphan")
        assert len(results) == 1
        server_name, _ = results[0]
        assert server_name == "unknown"

    def test_search_with_max_results_larger_than_matches(
        self, index: ToolSearchIndex
    ) -> None:
        """max_results larger than actual matches should return all matches."""
        results = index.search("multiply", max_results=100)
        # Should return matching results without error
        assert len(results) >= 1
        assert len(results) <= index.tool_count

    def test_server_filter_with_max_results(self, index: ToolSearchIndex) -> None:
        """max_results should apply after server filtering."""
        results = index.search("search", max_results=1, server_filter="search")
        assert len(results) <= 1
        if results:
            assert results[0][0] == "search"
