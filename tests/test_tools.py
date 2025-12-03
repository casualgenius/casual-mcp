"""Tests for tool models and converters."""

import pytest

from casual_mcp.convert_tools import (
    tool_from_mcp,
    tools_from_mcp,
)


class TestMCPConverters:
    """Tests for MCP format converters."""

    def test_tool_from_mcp(self):
        """Test converting from MCP tool format."""

        # Create a mock MCP tool
        class MockMCPTool:
            def __init__(self):
                self.name = "get_weather"
                self.description = "Get weather data"
                self.inputSchema = {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "City name"}},
                    "required": ["city"],
                }

        mcp_tool = MockMCPTool()
        tool = tool_from_mcp(mcp_tool)

        assert tool.name == "get_weather"
        assert tool.description == "Get weather data"
        assert "city" in tool.parameters
        assert tool.required == ["city"]

    def test_tool_from_mcp_missing_name(self):
        """Test that tool_from_mcp raises ValueError for missing name."""

        class MockMCPTool:
            def __init__(self):
                self.name = None
                self.description = "Description"
                self.inputSchema = {}

        with pytest.raises(ValueError, match="missing required fields"):
            tool_from_mcp(MockMCPTool())

    def test_tool_from_mcp_missing_description(self):
        """Test that tool_from_mcp raises ValueError for missing description."""

        class MockMCPTool:
            def __init__(self):
                self.name = "test"
                self.description = None
                self.inputSchema = {}

        with pytest.raises(ValueError, match="missing required fields"):
            tool_from_mcp(MockMCPTool())

    def test_tool_from_mcp_no_input_schema(self):
        """Test tool_from_mcp handles missing inputSchema gracefully."""

        class MockMCPTool:
            def __init__(self):
                self.name = "test"
                self.description = "Test"
                # No inputSchema attribute

        tool = tool_from_mcp(MockMCPTool())
        assert tool.name == "test"
        assert tool.parameters == {}
        assert tool.required == []

    def test_tools_from_mcp(self):
        """Test converting multiple MCP tools."""

        class MockMCPTool:
            def __init__(self, name):
                self.name = name
                self.description = f"Description for {name}"
                self.inputSchema = {}

        mcp_tools = [MockMCPTool("tool1"), MockMCPTool("tool2")]
        tools = tools_from_mcp(mcp_tools)

        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"

    def test_tools_from_mcp_skips_invalid(self):
        """Test that tools_from_mcp skips invalid tools."""

        class MockMCPTool:
            def __init__(self, name, description):
                self.name = name
                self.description = description
                self.inputSchema = {}

        mcp_tools = [
            MockMCPTool("valid", "Valid tool"),
            MockMCPTool(None, "Invalid - no name"),  # Should be skipped
            MockMCPTool("also_valid", "Another valid tool"),
        ]

        tools = tools_from_mcp(mcp_tools)

        # Should only have the 2 valid tools
        assert len(tools) == 2
        assert tools[0].name == "valid"
        assert tools[1].name == "also_valid"

    def test_tools_from_mcp_empty(self):
        """Test converting empty MCP tool list."""
        assert tools_from_mcp([]) == []
