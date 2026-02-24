"""Tests for SyntheticTool protocol and McpToolChat synthetic tool integration."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import mcp
import pytest
from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolCallFunction,
    Model,
    Tool,
    ToolParameter,
    UserMessage,
)

from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.synthetic_tool import SyntheticTool, SyntheticToolResult


class FakeSyntheticTool:
    """A concrete implementation of SyntheticTool for testing."""

    def __init__(
        self,
        tool_name: str = "search-tools",
        content: str = "Search results here",
        newly_loaded_tools: list[mcp.Tool] | None = None,
    ) -> None:
        self._name = tool_name
        self._content = content
        self._newly_loaded_tools = newly_loaded_tools or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def definition(self) -> Tool:
        return Tool(
            name=self._name,
            description=f"A synthetic tool named {self._name}",
            parameters={
                "query": ToolParameter(type="string", description="Search query"),
            },
            required=["query"],
        )

    async def execute(self, args: dict[str, Any]) -> SyntheticToolResult:
        return SyntheticToolResult(
            content=self._content,
            newly_loaded_tools=self._newly_loaded_tools,
        )


class ErrorSyntheticTool:
    """A synthetic tool that raises an error on execute."""

    @property
    def name(self) -> str:
        return "error_tool"

    @property
    def definition(self) -> Tool:
        return Tool(
            name="error_tool",
            description="A tool that always errors",
            parameters={},
            required=[],
        )

    async def execute(self, args: dict[str, Any]) -> SyntheticToolResult:
        raise RuntimeError("Synthetic tool failed")


class TestSyntheticToolResult:
    """Tests for SyntheticToolResult NamedTuple."""

    def test_create_with_positional_args(self) -> None:
        """Test creating SyntheticToolResult with positional arguments."""
        result = SyntheticToolResult("hello", [])
        assert result.content == "hello"
        assert result.newly_loaded_tools == []

    def test_create_with_keyword_args(self) -> None:
        """Test creating SyntheticToolResult with keyword arguments."""
        tools: list[mcp.Tool] = []
        result = SyntheticToolResult(content="result text", newly_loaded_tools=tools)
        assert result.content == "result text"
        assert result.newly_loaded_tools == []

    def test_create_with_newly_loaded_tools(self) -> None:
        """Test that newly_loaded_tools field accepts mcp.Tool instances."""
        mcp_tool = mcp.Tool(
            name="new_tool",
            description="A newly loaded tool",
            inputSchema={"type": "object", "properties": {}},
        )
        result = SyntheticToolResult(content="found tools", newly_loaded_tools=[mcp_tool])
        assert len(result.newly_loaded_tools) == 1
        assert result.newly_loaded_tools[0].name == "new_tool"

    def test_is_namedtuple(self) -> None:
        """Test that SyntheticToolResult is a NamedTuple with correct fields."""
        result = SyntheticToolResult("content", [])
        assert result._fields == ("content", "newly_loaded_tools")
        # NamedTuples are tuples
        assert isinstance(result, tuple)


class TestSyntheticToolProtocol:
    """Tests for SyntheticTool protocol conformance."""

    def test_fake_implements_protocol(self) -> None:
        """Test that FakeSyntheticTool satisfies SyntheticTool protocol."""
        tool: SyntheticTool = FakeSyntheticTool()
        assert tool.name == "search-tools"
        assert isinstance(tool.definition, Tool)

    def test_definition_has_correct_structure(self) -> None:
        """Test that the definition property returns a well-formed Tool."""
        tool = FakeSyntheticTool("my_tool")
        defn = tool.definition
        assert defn.name == "my_tool"
        assert defn.description
        assert "query" in defn.parameters

    async def test_execute_returns_synthetic_tool_result(self) -> None:
        """Test that execute returns a SyntheticToolResult."""
        tool = FakeSyntheticTool(content="test content")
        result = await tool.execute({"query": "test"})
        assert isinstance(result, SyntheticToolResult)
        assert result.content == "test content"
        assert result.newly_loaded_tools == []


class TestMcpToolChatSyntheticTools:
    """Tests for McpToolChat integration with synthetic tools."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create mock MCP client."""
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        """Create mock LLM model."""
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    @pytest.fixture
    def mock_tool_cache(self) -> Mock:
        """Create mock tool cache with no MCP tools."""
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        return cache

    def test_init_without_synthetic_tools(
        self, mock_client: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that McpToolChat works without synthetic tools (default)."""
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        assert chat._synthetic_registry == {}

    def test_init_with_synthetic_tools(self, mock_client: AsyncMock, mock_tool_cache: Mock) -> None:
        """Test that McpToolChat builds synthetic registry from provided tools."""
        tool1 = FakeSyntheticTool("tool_a")
        tool2 = FakeSyntheticTool("tool_b")

        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[tool1, tool2])

        assert len(chat._synthetic_registry) == 2
        assert "tool_a" in chat._synthetic_registry
        assert "tool_b" in chat._synthetic_registry

    async def test_chat_no_synthetic_tools_unchanged(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that chat behavior is unchanged when no synthetic tools are provided."""
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        messages = [UserMessage(content="Hello")]

        response = await chat.chat(messages, model=mock_model)

        assert len(response) == 1
        assert response[0].content == "Response"
        # model.chat should be called with empty tool list (no MCP tools, no synthetic)
        call_kwargs = mock_model.chat.call_args[1]
        assert call_kwargs["tools"] == []

    async def test_synthetic_tool_definitions_included_in_model_chat(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that synthetic tool definitions are included in model.chat(tools=...) call."""
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        await chat.chat([UserMessage(content="Hello")], model=mock_model)

        # Check the tools passed to model.chat
        call_kwargs = mock_model.chat.call_args[1]
        tools = call_kwargs["tools"]
        assert len(tools) == 1
        assert tools[0].name == "search-tools"

    async def test_synthetic_tool_definitions_combined_with_mcp_tools(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that synthetic tools are combined with MCP tools in model.chat()."""
        # Add an MCP tool to the cache
        mcp_tool = mcp.Tool(
            name="mcp_calculator",
            description="A calculator tool",
            inputSchema={"type": "object", "properties": {}},
        )
        mock_tool_cache.get_tools = AsyncMock(return_value=[mcp_tool])
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        await chat.chat([UserMessage(content="Hello")], model=mock_model)

        # Should have both MCP and synthetic tools
        call_kwargs = mock_model.chat.call_args[1]
        tools = call_kwargs["tools"]
        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert "mcp_calculator" in tool_names
        assert "search-tools" in tool_names

    async def test_synthetic_tool_intercepted_in_loop(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that synthetic tool calls are intercepted and not forwarded to MCP."""
        tool_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(
                name="search-tools", arguments='{"query": "calculator"}'
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )

        synthetic = FakeSyntheticTool("search-tools", content="Found: calculator tool")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        response = await chat.chat([UserMessage(content="Find calculator")], model=mock_model)

        # MCP client should NOT have been called
        mock_client.call_tool.assert_not_called()

        # Should have 3 messages: assistant (tool call), tool result, assistant (final)
        assert len(response) == 3
        assert response[0].tool_calls is not None  # first assistant msg with tool call
        assert response[1].content == "Found: calculator tool"  # tool result
        assert response[1].name == "search-tools"
        assert response[1].tool_call_id == "call_1"
        assert response[2].content == "Final response"  # final response

    async def test_synthetic_tool_result_message_format(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that synthetic tool result is returned as a proper ToolResultMessage."""
        tool_call = AssistantToolCall(
            id="call_42",
            function=AssistantToolCallFunction(name="search-tools", arguments='{"query": "test"}'),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Done"),
            ]
        )

        synthetic = FakeSyntheticTool("search-tools", content="Result content")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        response = await chat.chat([UserMessage(content="Test")], model=mock_model)

        tool_result = response[1]
        assert tool_result.role == "tool"
        assert tool_result.name == "search-tools"
        assert tool_result.tool_call_id == "call_42"
        assert tool_result.content == "Result content"

    async def test_mcp_tool_still_forwarded_when_synthetic_present(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that non-synthetic tool calls are still forwarded to MCP."""
        mcp_tool_call = AssistantToolCall(
            id="call_mcp",
            function=AssistantToolCallFunction(name="calculator", arguments='{"x": 1}'),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[mcp_tool_call]),
                AssistantMessage(content="Done"),
            ]
        )

        # Mock MCP tool execution
        class MockContent:
            type = "text"
            text = "42"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        await chat.chat([UserMessage(content="Calculate")], model=mock_model)

        # MCP client SHOULD have been called for the non-synthetic tool
        mock_client.call_tool.assert_called_once()

    async def test_mixed_synthetic_and_mcp_tool_calls(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test handling of both synthetic and MCP tool calls in the same response."""
        synthetic_call = AssistantToolCall(
            id="call_syn",
            function=AssistantToolCallFunction(name="search-tools", arguments='{"query": "calc"}'),
        )
        mcp_call = AssistantToolCall(
            id="call_mcp",
            function=AssistantToolCallFunction(name="calculator", arguments='{"x": 1}'),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[synthetic_call, mcp_call]),
                AssistantMessage(content="Done"),
            ]
        )

        # Mock MCP tool execution
        class MockContent:
            type = "text"
            text = "42"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        synthetic = FakeSyntheticTool("search-tools", content="Found calculator")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        response = await chat.chat([UserMessage(content="Test")], model=mock_model)

        # Should have: assistant (tool calls), synthetic result, mcp result, assistant (final)
        assert len(response) == 4
        assert response[1].name == "search-tools"
        assert response[1].content == "Found calculator"
        assert response[2].name == "calculator"

        # MCP client should only have been called for the non-synthetic tool
        mock_client.call_tool.assert_called_once()

    async def test_synthetic_tool_error_handled(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that errors from synthetic tool execution are handled gracefully."""
        tool_call = AssistantToolCall(
            id="call_err",
            function=AssistantToolCallFunction(name="error_tool", arguments="{}"),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="I see the error"),
            ]
        )

        error_tool = ErrorSyntheticTool()
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[error_tool])
        response = await chat.chat([UserMessage(content="Test")], model=mock_model)

        # Error should be surfaced to the LLM
        assert len(response) == 3
        error_result = response[1]
        assert error_result.name == "error_tool"
        assert "Error: Tool 'error_tool' failed to execute." in error_result.content


class TestSyntheticToolStats:
    """Tests for stats tracking of synthetic tool calls."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create mock MCP client."""
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        """Create mock LLM model."""
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    @pytest.fixture
    def mock_tool_cache(self) -> Mock:
        """Create mock tool cache with no MCP tools."""
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        return cache

    async def test_synthetic_tool_stats_tracked_under_synthetic_server(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that synthetic tool calls are tracked under '_synthetic' server."""
        tool_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="search-tools", arguments='{"query": "test"}'),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Done"),
            ]
        )

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool == {"search-tools": 1}
        assert stats.tool_calls.by_server == {"_synthetic": 1}
        assert stats.tool_calls.total == 1

    async def test_synthetic_tool_stats_multiple_calls(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that multiple synthetic tool calls are accumulated correctly."""
        call_1 = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="search-tools", arguments='{"query": "first"}'),
        )
        call_2 = AssistantToolCall(
            id="call_2",
            function=AssistantToolCallFunction(
                name="search-tools", arguments='{"query": "second"}'
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[call_1, call_2]),
                AssistantMessage(content="Done"),
            ]
        )

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[synthetic])
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool == {"search-tools": 2}
        assert stats.tool_calls.by_server == {"_synthetic": 2}
        assert stats.tool_calls.total == 2

    async def test_mixed_tool_stats(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test stats with both synthetic and MCP tool calls."""
        synthetic_call = AssistantToolCall(
            id="call_syn",
            function=AssistantToolCallFunction(name="search-tools", arguments='{"query": "calc"}'),
        )
        mcp_call = AssistantToolCall(
            id="call_mcp",
            function=AssistantToolCallFunction(name="math_add", arguments='{"a": 1, "b": 2}'),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[synthetic_call, mcp_call]),
                AssistantMessage(content="Done"),
            ]
        )

        # Mock MCP tool execution
        class MockContent:
            type = "text"
            text = "3"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        synthetic = FakeSyntheticTool("search-tools")
        chat = McpToolChat(
            mock_client,
            "System",
            mock_tool_cache,
            server_names={"math"},
            synthetic_tools=[synthetic],
        )
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool == {"search-tools": 1, "math_add": 1}
        assert stats.tool_calls.by_server == {"_synthetic": 1, "math": 1}
        assert stats.tool_calls.total == 2

    async def test_no_synthetic_tools_stats_unchanged(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that stats are unchanged when no synthetic tools are configured."""
        tool_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="math_add", arguments="{}"),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Done"),
            ]
        )

        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        # No synthetic tools
        chat = McpToolChat(mock_client, "System", mock_tool_cache, server_names={"math"})
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_server == {"math": 1}
        assert "_synthetic" not in stats.tool_calls.by_server

    async def test_synthetic_tool_error_still_tracked_in_stats(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Test that stats are tracked even when synthetic tool execution fails."""
        tool_call = AssistantToolCall(
            id="call_err",
            function=AssistantToolCallFunction(name="error_tool", arguments="{}"),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="I see the error"),
            ]
        )

        error_tool = ErrorSyntheticTool()
        chat = McpToolChat(mock_client, "System", mock_tool_cache, synthetic_tools=[error_tool])
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        # Stats should still be tracked despite the error
        assert stats.tool_calls.by_tool == {"error_tool": 1}
        assert stats.tool_calls.by_server == {"_synthetic": 1}
