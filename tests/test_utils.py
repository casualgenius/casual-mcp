"""Tests for utility functions."""

import json
from unittest.mock import patch

import pytest

from casual_llm import AssistantToolCall, AssistantToolCallFunction
from casual_mcp.utils import format_tool_call_result, load_config, render_system_prompt


class TestFormatToolCallResult:
    """Tests for format_tool_call_result function."""

    @pytest.fixture
    def tool_call(self):
        """Create a sample tool call."""
        return AssistantToolCall(
            id="call_123",
            function=AssistantToolCallFunction(
                name="get_weather", arguments='{"city": "London"}'
            ),
        )

    def test_format_result_only(self, tool_call):
        """Test formatting with style='result'."""
        result = format_tool_call_result(tool_call, "Sunny, 20°C", style="result")
        assert result == "Sunny, 20°C"

    def test_format_function_result(self, tool_call):
        """Test formatting with style='function_result'."""
        result = format_tool_call_result(tool_call, "Sunny, 20°C", style="function_result")
        assert result == "get_weather → Sunny, 20°C"

    def test_format_function_args_result(self, tool_call):
        """Test formatting with style='function_args_result'."""
        result = format_tool_call_result(tool_call, "Sunny, 20°C", style="function_args_result")
        assert result == "get_weather(city='London') → Sunny, 20°C"

    def test_format_with_id(self, tool_call):
        """Test formatting with include_id=True."""
        result = format_tool_call_result(
            tool_call, "Sunny, 20°C", style="result", include_id=True
        )
        assert result == "ID: call_123\nSunny, 20°C"

    def test_format_invalid_style(self, tool_call):
        """Test that invalid style raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported style"):
            format_tool_call_result(tool_call, "result", style="invalid")


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path):
        """Test loading a valid config file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "models": {"test-model": {"provider": "openai", "model": "gpt-4"}},
            "servers": {},
        }
        config_file.write_text(json.dumps(config_data))

        config = load_config(str(config_file))

        assert "test-model" in config.models
        assert config.models["test-model"].provider == "openai"

    def test_load_missing_file_raises(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")

    def test_load_invalid_json_raises(self, tmp_path):
        """Test that invalid JSON raises ValueError."""
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {")

        with pytest.raises(ValueError, match="Could not parse config JSON"):
            load_config(str(config_file))

    def test_load_invalid_schema_raises(self, tmp_path):
        """Test that invalid schema raises ValueError."""
        config_file = tmp_path / "config.json"
        config_data = {"invalid": "schema"}
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ValueError, match="Invalid config"):
            load_config(str(config_file))


class TestRenderSystemPrompt:
    """Tests for render_system_prompt function."""

    def test_render_template_with_tools(self, tmp_path):
        """Test rendering a template with tools."""
        # Create temporary template directory
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        # Create a simple template
        template_file = template_dir / "test.j2"
        template_file.write_text(
            "Tools: {% for tool in tools %}{{ tool.name }}{% if not loop.last %}, {% endif %}{% endfor %}"
        )

        # Mock tools
        class MockTool:
            def __init__(self, name):
                self.name = name

        tools = [MockTool("tool1"), MockTool("tool2")]

        # Patch TEMPLATE_DIR
        with patch("casual_mcp.utils.Path") as mock_path:
            mock_path.return_value.resolve.return_value = template_dir
            result = render_system_prompt("test.j2", tools)

        assert result == "Tools: tool1, tool2"

    def test_render_template_with_extra_vars(self, tmp_path):
        """Test rendering with extra variables."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        template_file = template_dir / "test.j2"
        template_file.write_text("{{ custom_var }}")

        with patch("casual_mcp.utils.Path") as mock_path:
            mock_path.return_value.resolve.return_value = template_dir
            result = render_system_prompt("test.j2", [], extra={"custom_var": "Hello"})

        assert result == "Hello"
