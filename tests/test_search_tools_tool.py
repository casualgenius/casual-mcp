"""Tests for manifest generation and SearchToolsTool."""

from typing import Any

import mcp
import pytest
from casual_llm import Tool

from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.search_tools_tool import (
    SearchToolsTool,
    _first_sentence,
    _format_param_details,
    _format_tool_details,
    _summarise_server,
    generate_manifest,
)
from casual_mcp.synthetic_tool import SyntheticToolResult
from casual_mcp.tool_search_index import ToolSearchIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
) -> mcp.Tool:
    """Create an mcp.Tool with optional custom input schema."""
    return mcp.Tool(
        name=name,
        description=description,
        inputSchema=input_schema or {"type": "object", "properties": {}},
    )


def _make_tool_with_params(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> mcp.Tool:
    """Create an mcp.Tool with typed parameters."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return mcp.Tool(name=name, description=description, inputSchema=schema)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def small_server_tools() -> dict[str, list[mcp.Tool]]:
    """Deferred tools grouped by server -- small servers (<= 10 tools)."""
    return {
        "weather": [
            _make_tool("weather_get_forecast", "Get weather forecast for a location."),
            _make_tool("weather_get_current", "Get current weather conditions."),
        ],
        "math": [
            _make_tool("math_add", "Add two numbers together."),
            _make_tool("math_multiply", "Multiply two numbers together."),
        ],
    }


@pytest.fixture
def large_server_tools() -> dict[str, list[mcp.Tool]]:
    """Deferred tools with a server that has >10 tools."""
    tools: list[mcp.Tool] = []
    for i in range(12):
        tools.append(_make_tool(f"bigserver_tool_{i}", f"Tool number {i} on big server."))
    return {"bigserver": tools}


@pytest.fixture
def all_deferred(
    small_server_tools: dict[str, list[mcp.Tool]],
) -> dict[str, list[mcp.Tool]]:
    """All small server deferred tools combined."""
    return small_server_tools


@pytest.fixture
def all_tools_flat(all_deferred: dict[str, list[mcp.Tool]]) -> list[mcp.Tool]:
    """Flat list of all deferred tools."""
    return [tool for tools in all_deferred.values() for tool in tools]


@pytest.fixture
def tool_server_map(all_deferred: dict[str, list[mcp.Tool]]) -> dict[str, str]:
    """Tool name -> server name mapping."""
    mapping: dict[str, str] = {}
    for server, tools in all_deferred.items():
        for tool in tools:
            mapping[tool.name] = server
    return mapping


@pytest.fixture
def search_index(
    all_tools_flat: list[mcp.Tool], tool_server_map: dict[str, str]
) -> ToolSearchIndex:
    """ToolSearchIndex built from all_deferred tools."""
    return ToolSearchIndex(all_tools_flat, tool_server_map)


@pytest.fixture
def config() -> ToolDiscoveryConfig:
    """Default tool discovery config."""
    return ToolDiscoveryConfig(enabled=True, max_search_results=5)


@pytest.fixture
def search_tool(
    all_deferred: dict[str, list[mcp.Tool]],
    search_index: ToolSearchIndex,
    config: ToolDiscoveryConfig,
) -> SearchToolsTool:
    """A SearchToolsTool instance for testing."""
    return SearchToolsTool(
        deferred_tools=all_deferred,
        server_names=["math", "weather"],
        search_index=search_index,
        config=config,
    )


# ===========================================================================
# _first_sentence tests
# ===========================================================================


class TestFirstSentence:
    """Tests for the _first_sentence helper."""

    def test_simple_sentence(self) -> None:
        assert _first_sentence("Hello world. More text.") == "Hello world."

    def test_single_sentence_with_period(self) -> None:
        assert _first_sentence("Hello world.") == "Hello world."

    def test_no_period(self) -> None:
        assert _first_sentence("Hello world") == "Hello world"

    def test_empty_string(self) -> None:
        assert _first_sentence("") == ""

    def test_leading_whitespace(self) -> None:
        assert _first_sentence("  Hello. World.") == "Hello."


# ===========================================================================
# _summarise_server tests
# ===========================================================================


class TestSummariseServer:
    """Tests for the _summarise_server helper."""

    def test_basic_summary(self) -> None:
        tools = [
            _make_tool("a", "First sentence. Extra."),
            _make_tool("b", "Second sentence. Extra."),
        ]
        result = _summarise_server(tools)
        assert "First sentence." in result
        assert "Second sentence." in result

    def test_deduplicates_same_description(self) -> None:
        tools = [
            _make_tool("a", "Same sentence. Extra."),
            _make_tool("b", "Same sentence. Extra."),
        ]
        result = _summarise_server(tools)
        assert result.count("Same sentence.") == 1

    def test_truncates_long_summary(self) -> None:
        tools = [
            _make_tool("a", "A" * 50 + ". More."),
            _make_tool("b", "B" * 50 + ". More."),
        ]
        result = _summarise_server(tools)
        assert len(result) <= 80
        assert result.endswith("...")

    def test_empty_descriptions(self) -> None:
        tools = [_make_tool("a", ""), _make_tool("b", "")]
        result = _summarise_server(tools)
        assert result == ""

    def test_none_descriptions(self) -> None:
        tools = [
            mcp.Tool(name="a", description=None, inputSchema={"type": "object", "properties": {}}),
        ]
        result = _summarise_server(tools)
        assert result == ""


# ===========================================================================
# generate_manifest tests
# ===========================================================================


class TestGenerateManifest:
    """Tests for the generate_manifest function."""

    def test_small_server_format(self, small_server_tools: dict[str, list[mcp.Tool]]) -> None:
        """Servers with <= 10 tools show all tool names."""
        manifest = generate_manifest(small_server_tools)
        assert "math (2 tools):" in manifest
        assert "weather (2 tools):" in manifest
        # All tool names should appear
        assert "math_add" in manifest
        assert "math_multiply" in manifest
        assert "weather_get_forecast" in manifest
        assert "weather_get_current" in manifest

    def test_large_server_truncation(self, large_server_tools: dict[str, list[mcp.Tool]]) -> None:
        """Servers with > 10 tools show first 4 names + '... and N more'."""
        manifest = generate_manifest(large_server_tools)
        assert "bigserver (12 tools):" in manifest
        assert "bigserver_tool_0" in manifest
        assert "bigserver_tool_3" in manifest
        assert "... and 8 more" in manifest
        # Tool 4+ should NOT be named
        assert "bigserver_tool_4" not in manifest

    def test_summary_descriptions_present(
        self, small_server_tools: dict[str, list[mcp.Tool]]
    ) -> None:
        manifest = generate_manifest(small_server_tools)
        # Summaries should appear indented on the line after the server header
        assert "  Add two numbers together." in manifest
        assert "  Get weather forecast for a location." in manifest

    def test_servers_sorted_alphabetically(
        self, small_server_tools: dict[str, list[mcp.Tool]]
    ) -> None:
        manifest = generate_manifest(small_server_tools)
        math_pos = manifest.index("- math")
        weather_pos = manifest.index("- weather")
        assert math_pos < weather_pos

    def test_empty_deferred(self) -> None:
        assert generate_manifest({}) == ""

    def test_single_server_single_tool(self) -> None:
        tools = {"solo": [_make_tool("solo_tool", "The only tool.")]}
        manifest = generate_manifest(tools)
        assert "solo (1 tool): solo_tool" in manifest
        assert "The only tool." in manifest

    def test_server_with_no_descriptions(self) -> None:
        """Server whose tools have no descriptions should not produce a summary line."""
        tools = {"bare": [_make_tool("bare_tool", "")]}
        manifest = generate_manifest(tools)
        assert "bare (1 tool): bare_tool" in manifest
        # No indented summary line
        lines = manifest.strip().split("\n")
        assert len(lines) == 1


# ===========================================================================
# _format_param_details tests
# ===========================================================================


class TestFormatParamDetails:
    """Tests for parameter formatting helper."""

    def test_no_properties(self) -> None:
        result = _format_param_details({"type": "object", "properties": {}})
        assert result == "  No parameters."

    def test_required_and_optional_params(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
                "units": {"type": "string", "description": "Temperature units"},
            },
            "required": ["location"],
        }
        result = _format_param_details(schema)
        assert "location: string (required)" in result
        assert "City name" in result
        assert "units: string" in result
        assert "units: string (required)" not in result

    def test_param_without_description(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"x": {"type": "number"}},
        }
        result = _format_param_details(schema)
        assert "x: number" in result


# ===========================================================================
# _format_tool_details tests
# ===========================================================================


class TestFormatToolDetails:
    """Tests for tool detail formatting."""

    def test_includes_server_and_tool_name(self) -> None:
        tool = _make_tool("weather_forecast", "Get the forecast.")
        result = _format_tool_details("weather", tool)
        assert "[weather]" in result
        assert "weather_forecast" in result
        assert "Get the forecast." in result

    def test_includes_parameters(self) -> None:
        tool = _make_tool_with_params(
            "math_add",
            "Add two numbers.",
            {"a": {"type": "number", "description": "First"}, "b": {"type": "number"}},
            required=["a", "b"],
        )
        result = _format_tool_details("math", tool)
        assert "a: number (required)" in result
        assert "b: number (required)" in result

    def test_tool_with_empty_description(self) -> None:
        tool = _make_tool("bare", "")
        result = _format_tool_details("srv", tool)
        assert "(no description)" in result

    def test_tool_with_none_description(self) -> None:
        tool = mcp.Tool(
            name="bare",
            description=None,
            inputSchema={"type": "object", "properties": {}},
        )
        result = _format_tool_details("srv", tool)
        assert "(no description)" in result


# ===========================================================================
# SearchToolsTool protocol conformance
# ===========================================================================


class TestSearchToolsToolProtocol:
    """Tests for SyntheticTool protocol conformance."""

    def test_name_property(self, search_tool: SearchToolsTool) -> None:
        assert search_tool.name == "search-tools"

    def test_definition_returns_tool(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        assert isinstance(defn, Tool)
        assert defn.name == "search-tools"

    def test_definition_has_query_param(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        assert "query" in defn.parameters

    def test_definition_has_server_name_param(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        assert "server_name" in defn.parameters

    def test_definition_has_tool_names_param(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        assert "tool_names" in defn.parameters
        assert defn.parameters["tool_names"].type == "array"

    def test_definition_no_required_params(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        assert defn.required == []

    def test_manifest_not_in_description(self, search_tool: SearchToolsTool) -> None:
        """Manifest should live in system_prompt, not the tool description."""
        defn = search_tool.definition
        assert "math (2 tools):" not in defn.description
        assert "weather (2 tools):" not in defn.description

    def test_valid_server_names_in_server_name_param(self, search_tool: SearchToolsTool) -> None:
        defn = search_tool.definition
        param_desc = defn.parameters["server_name"].description
        assert "math" in param_desc
        assert "weather" in param_desc

    def test_system_prompt_contains_manifest(self, search_tool: SearchToolsTool) -> None:
        prompt = search_tool.system_prompt
        assert "math (2 tools):" in prompt
        assert "weather (2 tools):" in prompt
        assert "search-tools" in prompt


# ===========================================================================
# execute() -- query only (BM25 search)
# ===========================================================================


class TestExecuteQueryOnly:
    """Tests for execute() with query parameter only."""

    async def test_query_returns_results(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"query": "weather forecast"})
        assert isinstance(result, SyntheticToolResult)
        assert "Found" in result.content
        assert len(result.newly_loaded_tools) > 0
        tool_names = {t.name for t in result.newly_loaded_tools}
        assert "weather_get_forecast" in tool_names

    async def test_query_result_includes_details(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"query": "add numbers"})
        assert "math_add" in result.content
        assert "Parameters:" in result.content

    async def test_query_no_matches(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"query": "xyzzynonexistent"})
        assert "No tools found" in result.content
        assert result.newly_loaded_tools == []

    async def test_query_respects_max_results(self) -> None:
        """max_search_results from config should limit results."""
        tools_map: dict[str, list[mcp.Tool]] = {
            "big": [_make_tool(f"big_tool_{i}", f"Tool {i} description") for i in range(20)]
        }
        all_tools = tools_map["big"]
        server_map = {t.name: "big" for t in all_tools}
        idx = ToolSearchIndex(all_tools, server_map)
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=3)
        st = SearchToolsTool(tools_map, ["big"], idx, cfg)
        result = await st.execute({"query": "tool description"})
        # Should be limited by max_search_results
        assert len(result.newly_loaded_tools) <= 3


# ===========================================================================
# execute() -- server_name only
# ===========================================================================


class TestExecuteServerNameOnly:
    """Tests for execute() with server_name parameter only."""

    async def test_server_name_loads_all_tools(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "math"})
        assert len(result.newly_loaded_tools) == 2
        names = {t.name for t in result.newly_loaded_tools}
        assert names == {"math_add", "math_multiply"}

    async def test_server_name_result_has_details(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "weather"})
        assert "weather_get_forecast" in result.content
        assert "weather_get_current" in result.content
        assert "Found 2 tool(s):" in result.content

    async def test_invalid_server_name(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "nonexistent"})
        assert "Error: Unknown server" in result.content
        assert "nonexistent" in result.content
        assert result.newly_loaded_tools == []

    async def test_invalid_server_shows_valid_servers(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "bad"})
        assert "math" in result.content
        assert "weather" in result.content


# ===========================================================================
# execute() -- tool_names only
# ===========================================================================


class TestExecuteToolNamesOnly:
    """Tests for execute() with tool_names parameter only."""

    async def test_exact_lookup_found(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"tool_names": ["math_add"]})
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_add"

    async def test_exact_lookup_multiple(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"tool_names": ["math_add", "weather_get_forecast"]})
        assert len(result.newly_loaded_tools) == 2
        names = {t.name for t in result.newly_loaded_tools}
        assert names == {"math_add", "weather_get_forecast"}

    async def test_exact_lookup_not_found(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"tool_names": ["missing_tool"]})
        assert "No tools found" in result.content
        assert result.newly_loaded_tools == []

    async def test_partial_found(self, search_tool: SearchToolsTool) -> None:
        """Some names found, some not."""
        result = await search_tool.execute({"tool_names": ["math_add", "nonexistent_tool"]})
        assert len(result.newly_loaded_tools) == 1
        assert "Not found: nonexistent_tool" in result.content

    async def test_empty_tool_names_treated_as_no_params(
        self, search_tool: SearchToolsTool
    ) -> None:
        result = await search_tool.execute({"tool_names": []})
        assert "Error: Please provide at least one" in result.content


# ===========================================================================
# execute() -- server_name + query (scoped search)
# ===========================================================================


class TestExecuteServerNamePlusQuery:
    """Tests for execute() with server_name + query."""

    async def test_scoped_search(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "weather", "query": "forecast"})
        assert len(result.newly_loaded_tools) >= 1
        for tool in result.newly_loaded_tools:
            assert "weather" in tool.name

    async def test_scoped_search_no_match(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "math", "query": "forecast"})
        assert "No tools found" in result.content
        assert result.newly_loaded_tools == []


# ===========================================================================
# execute() -- server_name + tool_names (scoped exact lookup)
# ===========================================================================


class TestExecuteServerNamePlusToolNames:
    """Tests for execute() with server_name + tool_names."""

    async def test_scoped_exact_lookup(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "math", "tool_names": ["math_add"]})
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_add"

    async def test_scoped_exact_lookup_filters_other_server(
        self, search_tool: SearchToolsTool
    ) -> None:
        """tool_names from wrong server should be filtered out."""
        result = await search_tool.execute(
            {"server_name": "math", "tool_names": ["weather_get_forecast"]}
        )
        # weather_get_forecast is not from math server, so filtered out
        assert "No tools found" in result.content
        assert result.newly_loaded_tools == []


# ===========================================================================
# execute() -- query + tool_names (tool_names takes precedence)
# ===========================================================================


class TestExecuteQueryPlusToolNames:
    """Tests for execute() with query + tool_names (tool_names takes precedence)."""

    async def test_tool_names_takes_precedence(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"query": "weather", "tool_names": ["math_add"]})
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_add"


# ===========================================================================
# execute() -- no params provided
# ===========================================================================


class TestExecuteNoParams:
    """Tests for execute() with no parameters."""

    async def test_no_params_returns_error(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({})
        assert "Error:" in result.content
        assert "at least one" in result.content
        assert result.newly_loaded_tools == []

    async def test_empty_string_query_treated_as_no_params(
        self, search_tool: SearchToolsTool
    ) -> None:
        result = await search_tool.execute({"query": ""})
        assert "Error:" in result.content

    async def test_whitespace_query_treated_as_no_params(
        self, search_tool: SearchToolsTool
    ) -> None:
        result = await search_tool.execute({"query": "   "})
        assert "Error:" in result.content


# ===========================================================================
# execute() -- already loaded tools
# ===========================================================================


class TestExecuteAlreadyLoaded:
    """Tests for handling already-loaded tools."""

    async def test_second_search_shows_already_loaded(self, search_tool: SearchToolsTool) -> None:
        """First call loads tools; second call reports them as already loaded."""
        result1 = await search_tool.execute({"tool_names": ["math_add"]})
        assert len(result1.newly_loaded_tools) == 1

        result2 = await search_tool.execute({"tool_names": ["math_add"]})
        assert len(result2.newly_loaded_tools) == 0
        assert "Already loaded: math_add" in result2.content

    async def test_mixed_new_and_already_loaded(self, search_tool: SearchToolsTool) -> None:
        # Load math_add first
        await search_tool.execute({"tool_names": ["math_add"]})

        # Now request both math_add (already loaded) and math_multiply (new)
        result = await search_tool.execute({"tool_names": ["math_add", "math_multiply"]})
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_multiply"
        assert "Already loaded: math_add" in result.content

    async def test_all_already_loaded(self, search_tool: SearchToolsTool) -> None:
        """When all requested tools are already loaded."""
        await search_tool.execute({"tool_names": ["math_add", "math_multiply"]})
        result = await search_tool.execute({"tool_names": ["math_add", "math_multiply"]})
        assert result.newly_loaded_tools == []
        assert "Already loaded:" in result.content
        # Should still show the tool details
        assert "Found 2 tool(s):" in result.content


# ===========================================================================
# execute() -- result format includes parameter details
# ===========================================================================


class TestExecuteResultFormat:
    """Tests for result text formatting including parameter details."""

    async def test_result_includes_param_details(self) -> None:
        tool = _make_tool_with_params(
            "math_add",
            "Add two numbers.",
            {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            required=["a", "b"],
        )
        deferred = {"math": [tool]}
        server_map = {"math_add": "math"}
        idx = ToolSearchIndex([tool], server_map)
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=5)
        st = SearchToolsTool(deferred, ["math"], idx, cfg)

        result = await st.execute({"tool_names": ["math_add"]})
        assert "a: number (required)" in result.content
        assert "b: number (required)" in result.content
        assert "First number" in result.content

    async def test_result_shows_optional_params(self) -> None:
        tool = _make_tool_with_params(
            "weather_forecast",
            "Get forecast.",
            {
                "location": {"type": "string", "description": "City"},
                "units": {"type": "string", "description": "Units"},
            },
            required=["location"],
        )
        deferred = {"weather": [tool]}
        server_map = {"weather_forecast": "weather"}
        idx = ToolSearchIndex([tool], server_map)
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=5)
        st = SearchToolsTool(deferred, ["weather"], idx, cfg)

        result = await st.execute({"tool_names": ["weather_forecast"]})
        assert "location: string (required)" in result.content
        assert "units: string" in result.content
        assert "units: string (required)" not in result.content


# ===========================================================================
# newly_loaded_tools correctness
# ===========================================================================


class TestNewlyLoadedTools:
    """Tests for newly_loaded_tools in SyntheticToolResult."""

    async def test_newly_loaded_contains_mcp_tools(self, search_tool: SearchToolsTool) -> None:
        result = await search_tool.execute({"server_name": "math"})
        for tool in result.newly_loaded_tools:
            assert isinstance(tool, mcp.Tool)

    async def test_newly_loaded_excludes_already_loaded(self, search_tool: SearchToolsTool) -> None:
        """Already-loaded tools should NOT appear in newly_loaded_tools."""
        await search_tool.execute({"tool_names": ["math_add"]})
        result = await search_tool.execute({"server_name": "math"})
        names = {t.name for t in result.newly_loaded_tools}
        assert "math_add" not in names
        assert "math_multiply" in names

    async def test_deferred_set_shrinks_after_load(self, search_tool: SearchToolsTool) -> None:
        assert "math_add" in search_tool._deferred_tools
        await search_tool.execute({"tool_names": ["math_add"]})
        assert "math_add" not in search_tool._deferred_tools
        assert "math_add" in search_tool._loaded_tools

    async def test_query_search_newly_loaded(self, search_tool: SearchToolsTool) -> None:
        """BM25 search should also move tools from deferred to loaded."""
        result = await search_tool.execute({"query": "add numbers"})
        # The results should include math_add
        if result.newly_loaded_tools:
            loaded_names = {t.name for t in result.newly_loaded_tools}
            for name in loaded_names:
                assert name not in search_tool._deferred_tools
                assert name in search_tool._loaded_tools


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Miscellaneous edge case tests."""

    async def test_empty_deferred_tools(self) -> None:
        """SearchToolsTool with no deferred tools."""
        idx = ToolSearchIndex([], {})
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=5)
        st = SearchToolsTool({}, [], idx, cfg)
        assert st.name == "search-tools"
        defn = st.definition
        assert isinstance(defn, Tool)

    async def test_execute_with_empty_deferred(self) -> None:
        idx = ToolSearchIndex([], {})
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=5)
        st = SearchToolsTool({}, [], idx, cfg)
        result = await st.execute({"query": "anything"})
        assert "No tools found" in result.content
        assert result.newly_loaded_tools == []

    async def test_tool_with_complex_schema(self) -> None:
        """Tool with nested/complex parameter schema."""
        tool = _make_tool_with_params(
            "complex_tool",
            "A complex tool.",
            {
                "config": {
                    "type": "object",
                    "description": "Configuration object",
                },
                "items": {
                    "type": "array",
                    "description": "List of items",
                },
            },
            required=["config"],
        )
        deferred = {"srv": [tool]}
        idx = ToolSearchIndex([tool], {"complex_tool": "srv"})
        cfg = ToolDiscoveryConfig(enabled=True, max_search_results=5)
        st = SearchToolsTool(deferred, ["srv"], idx, cfg)
        result = await st.execute({"tool_names": ["complex_tool"]})
        assert "config: object (required)" in result.content
        assert "items: array" in result.content

    async def test_server_name_with_empty_query_loads_server(
        self, search_tool: SearchToolsTool
    ) -> None:
        """server_name + empty query should just load the server (empty query normalized)."""
        result = await search_tool.execute({"server_name": "math", "query": ""})
        # empty query is normalized to None, so it falls through to server_name only path
        assert len(result.newly_loaded_tools) == 2

    async def test_all_three_params_tool_names_precedence(
        self, search_tool: SearchToolsTool
    ) -> None:
        """When all three params provided, tool_names takes precedence."""
        result = await search_tool.execute(
            {"query": "weather", "server_name": "math", "tool_names": ["math_add"]}
        )
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_add"

    async def test_duplicate_tool_names_handled(self, search_tool: SearchToolsTool) -> None:
        """Duplicate entries in tool_names should not cause errors."""
        result = await search_tool.execute({"tool_names": ["math_add", "math_add"]})
        # First occurrence is newly loaded, second is already loaded
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "math_add"
        assert "Already loaded: math_add" in result.content

    async def test_empty_server_name_treated_as_invalid(self, search_tool: SearchToolsTool) -> None:
        """Empty string server_name should produce an unknown server error."""
        result = await search_tool.execute({"server_name": ""})
        assert "Error: Unknown server" in result.content
        assert result.newly_loaded_tools == []

    def test_manifest_singular_tool_grammar(self) -> None:
        """Manifest should say '1 tool' not '1 tools'."""
        tools = {"solo": [_make_tool("solo_tool", "The only tool.")]}
        manifest = generate_manifest(tools)
        assert "1 tool)" in manifest
        assert "1 tools)" not in manifest

    def test_manifest_plural_tools_grammar(self) -> None:
        """Manifest should say 'N tools' for N > 1."""
        tools = {
            "multi": [
                _make_tool("tool_a", "First."),
                _make_tool("tool_b", "Second."),
            ]
        }
        manifest = generate_manifest(tools)
        assert "2 tools)" in manifest
