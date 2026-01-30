"""Tests for McpToolChat class."""

import pytest
from unittest.mock import AsyncMock, Mock

from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolCallFunction,
    UserMessage,
)
from casual_mcp.mcp_tool_chat import McpToolChat


class TestMcpToolChat:
    """Tests for McpToolChat class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock MCP client."""
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_provider(self):
        """Create mock LLM provider."""
        provider = AsyncMock()
        # get_usage is a sync method that returns Usage or None
        provider.get_usage = Mock(return_value=None)
        return provider

    @pytest.fixture
    def mock_tool_cache(self):
        """Create mock tool cache."""
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        return cache

    async def test_execute_tool_success(self, mock_client, mock_provider, mock_tool_cache):
        """Test successful tool execution."""
        # Setup
        tool_call = AssistantToolCall(
            id="call_123",
            function=AssistantToolCallFunction(name="test_tool", arguments='{"arg": "value"}'),
        )

        # Mock tool result
        class MockContent:
            text = "Tool result"

        class MockResult:
            content = [MockContent()]

        mock_client.call_tool = AsyncMock(return_value=MockResult())

        chat = McpToolChat(mock_client, mock_provider, "system prompt", mock_tool_cache)

        # Execute
        result = await chat.execute(tool_call)

        # Verify
        assert result.name == "test_tool"
        assert result.tool_call_id == "call_123"
        assert "Tool result" in result.content
        mock_client.call_tool.assert_called_once_with("test_tool", {"arg": "value"})

    async def test_execute_tool_handles_error(self, mock_client, mock_provider, mock_tool_cache):
        """Test that tool execution handles errors."""
        tool_call = AssistantToolCall(
            id="call_123", function=AssistantToolCallFunction(name="test_tool", arguments="{}")
        )

        mock_client.call_tool = AsyncMock(side_effect=ValueError("Tool error"))

        chat = McpToolChat(mock_client, mock_provider, "system prompt", mock_tool_cache)
        result = await chat.execute(tool_call)

        # Should return error message
        assert "Tool error" in result.content

    async def test_execute_tool_handles_non_text_content(
        self, mock_client, mock_provider, mock_tool_cache
    ):
        """Test that tool execution handles non-text content gracefully."""
        tool_call = AssistantToolCall(
            id="call_123", function=AssistantToolCallFunction(name="test_tool", arguments="{}")
        )

        # Mock non-text content (e.g., ImageContent)
        class MockImageContent:
            # No text attribute
            pass

        class MockResult:
            content = [MockImageContent()]

        mock_client.call_tool = AsyncMock(return_value=MockResult())

        chat = McpToolChat(mock_client, mock_provider, "system prompt", mock_tool_cache)
        result = await chat.execute(tool_call)

        # Should handle gracefully
        assert "Non-text content" in result.content

    async def test_chat_adds_system_message(self, mock_client, mock_provider, mock_tool_cache):
        """Test that chat adds system message if not present."""
        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, mock_provider, "System prompt", mock_tool_cache)
        messages = [UserMessage(content="Hello")]

        await chat.chat(messages)

        # Should have added system message
        assert len(messages) >= 2
        assert messages[0].role == "system"

    async def test_chat_doesnt_duplicate_system_message(
        self, mock_client, mock_provider, mock_tool_cache
    ):
        """Test that chat doesn't add system message if already present."""
        from casual_llm import SystemMessage

        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, mock_provider, "System prompt", mock_tool_cache)
        messages = [SystemMessage(content="Existing system"), UserMessage(content="Hello")]

        await chat.chat(messages)

        # Should not add another system message
        system_messages = [m for m in messages if m.role == "system"]
        assert len(system_messages) == 1

    async def test_chat_loops_on_tool_calls(self, mock_client, mock_provider, mock_tool_cache):
        """Test that chat loops when LLM requests tool calls."""
        # First response has tool call, second doesn't
        tool_call = AssistantToolCall(
            id="call_1", function=AssistantToolCallFunction(name="tool1", arguments="{}")
        )

        mock_provider.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )

        # Mock tool execution
        class MockContent:
            text = "result"

        mock_client.call_tool = AsyncMock(return_value=Mock(content=[MockContent()]))

        chat = McpToolChat(mock_client, mock_provider, "System", mock_tool_cache)
        messages = [UserMessage(content="Test")]

        response = await chat.chat(messages)

        # Should have called provider twice (once for tool call, once for final)
        assert mock_provider.chat.call_count == 2
        assert len(response) >= 2  # At least assistant message and tool result

    async def test_chat_stops_when_no_tool_calls(self, mock_client, mock_provider, mock_tool_cache):
        """Test that chat stops when LLM doesn't request tool calls."""
        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Final response"))

        chat = McpToolChat(mock_client, mock_provider, "System", mock_tool_cache)
        messages = [UserMessage(content="Test")]

        response = await chat.chat(messages)

        # Should have called provider once
        assert mock_provider.chat.call_count == 1
        assert len(response) == 1
        assert response[0].content == "Final response"

    async def test_generate_creates_user_message(self, mock_client, mock_provider, mock_tool_cache):
        """Test that generate creates a UserMessage from prompt."""
        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, mock_provider, "System", mock_tool_cache)

        await chat.generate("Hello")

        # Should have called chat with UserMessage
        call_args = mock_provider.chat.call_args
        messages = call_args[1]["messages"]

        # Should have system + user message
        user_messages = [m for m in messages if m.role == "user"]
        assert len(user_messages) == 1
        assert user_messages[0].content == "Hello"

    async def test_generate_with_session_retrieves_messages(
        self, mock_client, mock_provider, mock_tool_cache
    ):
        """Test that generate with session_id retrieves session messages."""
        from casual_mcp.mcp_tool_chat import sessions

        sessions["test_session"] = [UserMessage(content="Previous message")]

        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, mock_provider, "System", mock_tool_cache)

        await chat.generate("New message", session_id="test_session")

        # Should have included previous message
        call_args = mock_provider.chat.call_args
        messages = call_args[1]["messages"]

        user_messages = [m for m in messages if m.role == "user"]
        assert len(user_messages) == 2  # Previous + new

        # Cleanup
        sessions.clear()

    async def test_generate_with_session_adds_responses(
        self, mock_client, mock_provider, mock_tool_cache
    ):
        """Test that generate with session adds responses to session."""
        from casual_mcp.mcp_tool_chat import sessions

        mock_provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, mock_provider, "System", mock_tool_cache)

        await chat.generate("Message", session_id="test_session")

        # Session should have user message and assistant response
        assert len(sessions["test_session"]) == 2

        # Cleanup
        sessions.clear()

    def test_get_session_returns_session(self, mock_client, mock_provider, mock_tool_cache):
        """Test that get_session returns the correct session."""
        from casual_mcp.mcp_tool_chat import sessions

        sessions["test"] = [UserMessage(content="Test")]

        result = McpToolChat.get_session("test")

        assert result is not None
        assert len(result) == 1

        # Cleanup
        sessions.clear()

    def test_get_session_returns_none_for_nonexistent(
        self, mock_client, mock_provider, mock_tool_cache
    ):
        """Test that get_session returns None for nonexistent session."""
        result = McpToolChat.get_session("nonexistent")

        assert result is None


class TestMcpToolChatStats:
    """Tests for McpToolChat stats functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock MCP client."""
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_tool_cache(self):
        """Create mock tool cache."""
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        return cache

    def test_get_stats_returns_none_before_chat(self, mock_client, mock_tool_cache):
        """Test that get_stats returns None before any chat calls."""
        provider = AsyncMock()
        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)

        assert chat.get_stats() is None

    async def test_get_stats_returns_stats_after_chat(self, mock_client, mock_tool_cache):
        """Test that get_stats returns stats after chat call."""
        from casual_llm import Usage

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        provider.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Hello")])

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tokens.prompt_tokens == 10
        assert stats.tokens.completion_tokens == 5
        assert stats.tokens.total_tokens == 15
        assert stats.llm_calls == 1

    async def test_stats_reset_on_new_chat(self, mock_client, mock_tool_cache):
        """Test that stats are reset at the start of each chat call."""
        from casual_llm import Usage

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        provider.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)

        # First chat
        await chat.chat([UserMessage(content="First")])
        stats1 = chat.get_stats()
        assert stats1.tokens.prompt_tokens == 10

        # Second chat - stats should be fresh, not accumulated
        await chat.chat([UserMessage(content="Second")])
        stats2 = chat.get_stats()
        assert stats2.tokens.prompt_tokens == 10  # Not 20

    async def test_stats_accumulate_across_llm_calls(self, mock_client, mock_tool_cache):
        """Test that token usage accumulates across multiple LLM calls in one chat."""
        from casual_llm import Usage

        tool_call = AssistantToolCall(
            id="call_1", function=AssistantToolCallFunction(name="math_add", arguments="{}")
        )

        provider = AsyncMock()
        provider.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )
        # Return different usage for each call
        provider.get_usage = Mock(
            side_effect=[
                Usage(prompt_tokens=100, completion_tokens=20),
                Usage(prompt_tokens=150, completion_tokens=30),
            ]
        )

        # Mock tool execution
        class MockContent:
            text = "result"

        mock_client.call_tool = AsyncMock(return_value=Mock(content=[MockContent()]))

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Test")])

        stats = chat.get_stats()
        assert stats.llm_calls == 2
        assert stats.tokens.prompt_tokens == 250  # 100 + 150
        assert stats.tokens.completion_tokens == 50  # 20 + 30
        assert stats.tokens.total_tokens == 300

    async def test_stats_track_tool_usage(self, mock_client, mock_tool_cache):
        """Test that tool usage is tracked by tool name and server."""
        from casual_llm import Usage

        tool_calls = [
            AssistantToolCall(
                id="call_1", function=AssistantToolCallFunction(name="math_add", arguments="{}")
            ),
            AssistantToolCall(
                id="call_2", function=AssistantToolCallFunction(name="math_add", arguments="{}")
            ),
            AssistantToolCall(
                id="call_3",
                function=AssistantToolCallFunction(name="words_define", arguments="{}"),
            ),
        ]

        provider = AsyncMock()
        provider.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=tool_calls),
                AssistantMessage(content="Final response"),
            ]
        )
        provider.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        # Mock tool execution
        class MockContent:
            text = "result"

        mock_client.call_tool = AsyncMock(return_value=Mock(content=[MockContent()]))

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Test")])

        stats = chat.get_stats()
        assert stats.tool_calls.by_tool == {"math_add": 2, "words_define": 1}
        assert stats.tool_calls.by_server == {"math": 2, "words": 1}
        assert stats.tool_calls.total == 3

    async def test_stats_handle_unprefixed_tool_names(self, mock_client, mock_tool_cache):
        """Test that unprefixed tool names use 'default' as server."""
        from casual_llm import Usage

        tool_call = AssistantToolCall(
            id="call_1", function=AssistantToolCallFunction(name="simple_tool", arguments="{}")
        )

        provider = AsyncMock()
        provider.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )
        provider.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        # Mock tool execution
        class MockContent:
            text = "result"

        mock_client.call_tool = AsyncMock(return_value=Mock(content=[MockContent()]))

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Test")])

        stats = chat.get_stats()
        # "simple_tool" has underscore so splits to "simple" as server
        assert stats.tool_calls.by_server == {"simple": 1}

    async def test_stats_handle_no_usage_from_provider(self, mock_client, mock_tool_cache):
        """Test that stats handle providers that return None for usage."""
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        provider.get_usage = Mock(return_value=None)

        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Hello")])

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tokens.prompt_tokens == 0
        assert stats.tokens.completion_tokens == 0
        assert stats.llm_calls == 1

    def test_extract_server_from_tool_name(self, mock_client, mock_tool_cache):
        """Test server name extraction from tool names."""
        provider = AsyncMock()
        chat = McpToolChat(mock_client, provider, "System", mock_tool_cache)

        assert chat._extract_server_from_tool_name("math_add") == "math"
        assert chat._extract_server_from_tool_name("words_define") == "words"
        assert chat._extract_server_from_tool_name("server_name_tool") == "server"
        assert chat._extract_server_from_tool_name("notool") == "default"
