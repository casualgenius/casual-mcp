"""Tests for chat statistics models."""


from casual_mcp.models.chat_stats import (
    ChatStats,
    TokenUsageStats,
    ToolUsageStats,
)


class TestTokenUsageStats:
    """Tests for TokenUsageStats model."""

    def test_total_tokens_computed(self):
        """Test that total_tokens is correctly computed."""
        stats = TokenUsageStats(prompt_tokens=100, completion_tokens=50)
        assert stats.total_tokens == 150

    def test_defaults_to_zero(self):
        """Test that fields default to zero."""
        stats = TokenUsageStats()
        assert stats.prompt_tokens == 0
        assert stats.completion_tokens == 0
        assert stats.total_tokens == 0

    def test_serialization_includes_total(self):
        """Test that serialization includes computed total_tokens."""
        stats = TokenUsageStats(prompt_tokens=10, completion_tokens=5)
        data = stats.model_dump()
        assert data["prompt_tokens"] == 10
        assert data["completion_tokens"] == 5
        assert data["total_tokens"] == 15


class TestToolUsageStats:
    """Tests for ToolUsageStats model."""

    def test_total_tool_calls(self):
        """Test that total_tool_calls is correctly computed."""
        stats = ToolUsageStats(
            by_tool={"math_add": 2, "words_define": 1},
            by_server={"math": 2, "words": 1},
        )
        assert stats.total_tool_calls == 3

    def test_empty_defaults(self):
        """Test that fields default to empty dicts."""
        stats = ToolUsageStats()
        assert stats.by_tool == {}
        assert stats.by_server == {}
        assert stats.total_tool_calls == 0

    def test_serialization_includes_total(self):
        """Test that serialization includes computed total_tool_calls."""
        stats = ToolUsageStats(by_tool={"add": 1, "subtract": 2}, by_server={"math": 3})
        data = stats.model_dump()
        assert data["by_tool"] == {"add": 1, "subtract": 2}
        assert data["by_server"] == {"math": 3}
        assert data["total_tool_calls"] == 3


class TestChatStats:
    """Tests for ChatStats model."""

    def test_defaults(self):
        """Test that ChatStats has sensible defaults."""
        stats = ChatStats()
        assert stats.tokens.prompt_tokens == 0
        assert stats.tokens.completion_tokens == 0
        assert stats.tools.by_tool == {}
        assert stats.tools.by_server == {}
        assert stats.llm_calls == 0

    def test_nested_structure(self):
        """Test that nested stats are properly created."""
        stats = ChatStats(
            tokens=TokenUsageStats(prompt_tokens=100, completion_tokens=50),
            tools=ToolUsageStats(by_tool={"add": 1}, by_server={"math": 1}),
            llm_calls=2,
        )
        assert stats.tokens.total_tokens == 150
        assert stats.tools.total_tool_calls == 1
        assert stats.llm_calls == 2

    def test_serialization(self):
        """Test full serialization of ChatStats."""
        stats = ChatStats(
            tokens=TokenUsageStats(prompt_tokens=100, completion_tokens=50),
            tools=ToolUsageStats(by_tool={"add": 1}, by_server={"math": 1}),
            llm_calls=2,
        )
        data = stats.model_dump()
        assert data["tokens"]["prompt_tokens"] == 100
        assert data["tokens"]["completion_tokens"] == 50
        assert data["tokens"]["total_tokens"] == 150
        assert data["tools"]["by_tool"]["add"] == 1
        assert data["tools"]["by_server"]["math"] == 1
        assert data["tools"]["total_tool_calls"] == 1
        assert data["llm_calls"] == 2

    def test_mutable_stats(self):
        """Test that stats can be mutated during accumulation."""
        stats = ChatStats()

        # Simulate accumulating token usage
        stats.tokens.prompt_tokens += 50
        stats.tokens.completion_tokens += 25
        assert stats.tokens.total_tokens == 75

        # Simulate accumulating tool usage
        stats.tools.by_tool["add"] = stats.tools.by_tool.get("add", 0) + 1
        stats.tools.by_tool["add"] = stats.tools.by_tool.get("add", 0) + 1
        stats.tools.by_server["math"] = 2
        assert stats.tools.total_tool_calls == 2

        # Simulate LLM call count
        stats.llm_calls += 1
        stats.llm_calls += 1
        assert stats.llm_calls == 2
