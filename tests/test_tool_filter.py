"""Tests for tool filtering logic."""

import pytest

from casual_mcp.models.toolset_config import ExcludeSpec, ToolSetConfig
from casual_mcp.tool_filter import (
    ToolSetValidationError,
    extract_server_and_tool,
    filter_tools_by_toolset,
    validate_toolset,
)


class MockTool:
    """Mock MCP tool for testing."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description or f"Description for {name}"


class TestExtractServerAndTool:
    """Tests for extract_server_and_tool function."""

    def test_prefixed_tool_name(self):
        """Test extracting server from prefixed tool name."""
        server_names = {"search", "weather", "time"}
        server, base = extract_server_and_tool("search_brave_web_search", server_names)
        assert server == "search"
        assert base == "brave_web_search"

    def test_prefixed_tool_name_with_underscore_in_tool(self):
        """Test that only the first underscore is used as separator."""
        server_names = {"api", "data"}
        server, base = extract_server_and_tool("api_get_user_info", server_names)
        assert server == "api"
        assert base == "get_user_info"

    def test_single_server_no_prefix(self):
        """Test tool name without prefix when single server configured."""
        server_names = {"math"}
        server, base = extract_server_and_tool("add", server_names)
        assert server == "math"
        assert base == "add"

    def test_prefix_not_in_servers(self):
        """Test when prefix doesn't match any server."""
        server_names = {"weather", "time"}
        server, base = extract_server_and_tool("unknown_tool", server_names)
        # Falls back to single server case or default
        assert server == "default"
        assert base == "unknown_tool"

    def test_no_underscore_multiple_servers(self):
        """Test tool without underscore with multiple servers."""
        server_names = {"search", "weather"}
        server, base = extract_server_and_tool("sometool", server_names)
        assert server == "default"
        assert base == "sometool"


class TestValidateToolset:
    """Tests for validate_toolset function."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools from multiple servers."""
        return [
            MockTool("search_brave_web_search"),
            MockTool("search_brave_local_search"),
            MockTool("weather_get_forecast"),
            MockTool("weather_get_current"),
            MockTool("time_get_current_time"),
        ]

    @pytest.fixture
    def server_names(self):
        """Server names matching the mock tools."""
        return {"search", "weather", "time"}

    def test_valid_toolset_all_tools(self, mock_tools, server_names):
        """Test validation passes for toolset with all tools."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": True, "weather": True},
        )
        # Should not raise
        validate_toolset(toolset, mock_tools, server_names)

    def test_valid_toolset_include_list(self, mock_tools, server_names):
        """Test validation passes for toolset with include list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": ["brave_web_search"]},
        )
        validate_toolset(toolset, mock_tools, server_names)

    def test_valid_toolset_exclude_list(self, mock_tools, server_names):
        """Test validation passes for toolset with exclude list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": ExcludeSpec(exclude=["brave_local_search"])},
        )
        validate_toolset(toolset, mock_tools, server_names)

    def test_invalid_server(self, mock_tools, server_names):
        """Test validation fails for non-existent server."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"nonexistent": True},
        )
        with pytest.raises(ToolSetValidationError) as exc_info:
            validate_toolset(toolset, mock_tools, server_names)
        assert "nonexistent" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_invalid_tool_in_include(self, mock_tools, server_names):
        """Test validation fails for non-existent tool in include list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": ["nonexistent_tool"]},
        )
        with pytest.raises(ToolSetValidationError) as exc_info:
            validate_toolset(toolset, mock_tools, server_names)
        assert "nonexistent_tool" in str(exc_info.value)
        assert "search" in str(exc_info.value)

    def test_invalid_tool_in_exclude(self, mock_tools, server_names):
        """Test validation fails for non-existent tool in exclude list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"weather": ExcludeSpec(exclude=["nonexistent_tool"])},
        )
        with pytest.raises(ToolSetValidationError) as exc_info:
            validate_toolset(toolset, mock_tools, server_names)
        assert "nonexistent_tool" in str(exc_info.value)
        assert "exclude" in str(exc_info.value)

    def test_multiple_errors(self, mock_tools, server_names):
        """Test that all validation errors are collected."""
        toolset = ToolSetConfig(
            description="Test",
            servers={
                "nonexistent1": True,
                "nonexistent2": True,
            },
        )
        with pytest.raises(ToolSetValidationError) as exc_info:
            validate_toolset(toolset, mock_tools, server_names)
        error_msg = str(exc_info.value)
        assert "nonexistent1" in error_msg
        assert "nonexistent2" in error_msg


class TestFilterToolsByToolset:
    """Tests for filter_tools_by_toolset function."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools from multiple servers."""
        return [
            MockTool("search_brave_web_search"),
            MockTool("search_brave_local_search"),
            MockTool("search_brave_image_search"),
            MockTool("weather_get_forecast"),
            MockTool("weather_get_current"),
            MockTool("time_get_current_time"),
        ]

    @pytest.fixture
    def server_names(self):
        """Server names matching the mock tools."""
        return {"search", "weather", "time"}

    def test_filter_all_tools_from_server(self, mock_tools, server_names):
        """Test filtering with True (all tools from server)."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": True},
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 3
        names = [t.name for t in filtered]
        assert "search_brave_web_search" in names
        assert "search_brave_local_search" in names
        assert "search_brave_image_search" in names

    def test_filter_specific_tools(self, mock_tools, server_names):
        """Test filtering with include list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": ["brave_web_search", "brave_local_search"]},
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 2
        names = [t.name for t in filtered]
        assert "search_brave_web_search" in names
        assert "search_brave_local_search" in names
        assert "search_brave_image_search" not in names

    def test_filter_exclude_tools(self, mock_tools, server_names):
        """Test filtering with exclude list."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"search": ExcludeSpec(exclude=["brave_local_search"])},
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 2
        names = [t.name for t in filtered]
        assert "search_brave_web_search" in names
        assert "search_brave_image_search" in names
        assert "search_brave_local_search" not in names

    def test_filter_multiple_servers(self, mock_tools, server_names):
        """Test filtering across multiple servers."""
        toolset = ToolSetConfig(
            description="Test",
            servers={
                "search": ["brave_web_search"],
                "weather": True,
            },
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 3
        names = [t.name for t in filtered]
        assert "search_brave_web_search" in names
        assert "weather_get_forecast" in names
        assert "weather_get_current" in names

    def test_filter_mixed_specs(self, mock_tools, server_names):
        """Test filtering with mixed specification types."""
        toolset = ToolSetConfig(
            description="Test",
            servers={
                "search": True,  # all
                "weather": ["get_forecast"],  # include specific
                "time": ExcludeSpec(exclude=["get_current_time"]),  # exclude (results in nothing)
            },
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        names = [t.name for t in filtered]
        # All search tools
        assert "search_brave_web_search" in names
        assert "search_brave_local_search" in names
        assert "search_brave_image_search" in names
        # Only get_forecast from weather
        assert "weather_get_forecast" in names
        assert "weather_get_current" not in names
        # Time excluded current_time, nothing left
        assert "time_get_current_time" not in names

    def test_filter_empty_toolset(self, mock_tools, server_names):
        """Test filtering with empty toolset returns no tools."""
        toolset = ToolSetConfig(description="Empty", servers={})
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 0

    def test_filter_server_not_in_toolset_excluded(self, mock_tools, server_names):
        """Test that servers not in toolset are excluded."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"time": True},
        )
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names)

        assert len(filtered) == 1
        assert filtered[0].name == "time_get_current_time"

    def test_filter_without_validation(self, mock_tools, server_names):
        """Test filtering with validation disabled."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"nonexistent": True},  # Invalid server
        )
        # Should not raise when validate=False
        filtered = filter_tools_by_toolset(mock_tools, toolset, server_names, validate=False)

        # But should return no tools since server doesn't exist
        assert len(filtered) == 0

    def test_filter_with_validation_raises(self, mock_tools, server_names):
        """Test filtering with validation enabled raises on invalid."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"nonexistent": True},
        )
        with pytest.raises(ToolSetValidationError):
            filter_tools_by_toolset(mock_tools, toolset, server_names, validate=True)


class TestSingleServerScenario:
    """Tests for single server scenario (no tool name prefixing)."""

    @pytest.fixture
    def mock_tools_single_server(self):
        """Create mock tools from a single server (no prefix)."""
        return [
            MockTool("add"),
            MockTool("subtract"),
            MockTool("multiply"),
            MockTool("divide"),
        ]

    @pytest.fixture
    def single_server_names(self):
        """Single server name."""
        return {"math"}

    def test_filter_all_tools_single_server(self, mock_tools_single_server, single_server_names):
        """Test filtering all tools from single server."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"math": True},
        )
        filtered = filter_tools_by_toolset(mock_tools_single_server, toolset, single_server_names)

        assert len(filtered) == 4

    def test_filter_specific_tools_single_server(
        self, mock_tools_single_server, single_server_names
    ):
        """Test filtering specific tools from single server."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"math": ["add", "subtract"]},
        )
        filtered = filter_tools_by_toolset(mock_tools_single_server, toolset, single_server_names)

        assert len(filtered) == 2
        names = [t.name for t in filtered]
        assert "add" in names
        assert "subtract" in names

    def test_filter_exclude_tools_single_server(
        self, mock_tools_single_server, single_server_names
    ):
        """Test filtering with exclude on single server."""
        toolset = ToolSetConfig(
            description="Test",
            servers={"math": ExcludeSpec(exclude=["divide"])},
        )
        filtered = filter_tools_by_toolset(mock_tools_single_server, toolset, single_server_names)

        assert len(filtered) == 3
        names = [t.name for t in filtered]
        assert "divide" not in names
