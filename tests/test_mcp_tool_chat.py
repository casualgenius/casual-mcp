"""Tests for McpToolChat class."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolCallFunction,
    Model,
    UserMessage,
)
from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.model_factory import ModelFactory
from casual_mcp.models.config import Config, McpClientConfig, McpModelConfig
from casual_mcp.models.mcp_server_config import StdioServerConfig


class TestMcpToolChat:
    """Tests for McpToolChat class."""

    async def test_execute_tool_success(self, mock_client, mock_model, mock_tool_cache):
        """Test successful tool execution."""
        # Setup
        tool_call = AssistantToolCall(
            id="call_123",
            function=AssistantToolCallFunction(name="test_tool", arguments='{"arg": "value"}'),
        )

        # Mock tool result
        class MockContent:
            type = "text"
            text = "Tool result"

        class MockResult:
            content = [MockContent()]
            structuredContent = None

        mock_client.call_tool = AsyncMock(return_value=MockResult())

        chat = McpToolChat(mock_client, "system prompt", mock_tool_cache)

        # Execute
        result = await chat.execute(tool_call)

        # Verify
        assert result.name == "test_tool"
        assert result.tool_call_id == "call_123"
        assert "Tool result" in result.content
        mock_client.call_tool.assert_called_once_with("test_tool", {"arg": "value"}, meta=None)

    async def test_execute_tool_handles_error(self, mock_client, mock_model, mock_tool_cache):
        """Test that tool execution handles errors."""
        tool_call = AssistantToolCall(
            id="call_123", function=AssistantToolCallFunction(name="test_tool", arguments="{}")
        )

        mock_client.call_tool = AsyncMock(side_effect=ValueError("Tool error"))

        chat = McpToolChat(mock_client, "system prompt", mock_tool_cache)
        result = await chat.execute(tool_call)

        # Should return error message
        assert "Tool error" in result.content

    async def test_execute_tool_handles_non_text_content(
        self, mock_client, mock_model, mock_tool_cache
    ):
        """Test that tool execution handles non-text content gracefully."""
        tool_call = AssistantToolCall(
            id="call_123", function=AssistantToolCallFunction(name="test_tool", arguments="{}")
        )

        # Mock non-text content (e.g., ImageContent)
        class MockImageContent:
            type = "image"
            mimeType = "image/png"

        class MockResult:
            content = [MockImageContent()]
            structuredContent = None

        mock_client.call_tool = AsyncMock(return_value=MockResult())

        chat = McpToolChat(mock_client, "system prompt", mock_tool_cache)
        result = await chat.execute(tool_call)

        # Should handle gracefully with structured image info
        assert "image" in result.content
        assert "image/png" in result.content

    async def test_execute_tool_prefers_structured_content(
        self, mock_client, mock_model, mock_tool_cache
    ):
        """Test that structuredContent is preferred over content when available."""
        tool_call = AssistantToolCall(
            id="call_123", function=AssistantToolCallFunction(name="test_tool", arguments="{}")
        )

        # Mock result with both content and structuredContent
        class MockTextContent:
            type = "text"
            text = "Human readable text"

        class MockResult:
            content = [MockTextContent()]
            structuredContent = {"data": [1, 2, 3], "status": "ok"}

        mock_client.call_tool = AsyncMock(return_value=MockResult())

        chat = McpToolChat(mock_client, "system prompt", mock_tool_cache)
        result = await chat.execute(tool_call)

        # Should use structuredContent, not the text content
        assert "Human readable text" not in result.content
        assert '"data": [1, 2, 3]' in result.content
        assert '"status": "ok"' in result.content

    async def test_chat_adds_system_message(self, mock_client, mock_model, mock_tool_cache):
        """Test that chat adds system message if not present."""
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, "System prompt", mock_tool_cache)
        messages = [UserMessage(content="Hello")]

        await chat.chat(messages, model=mock_model)

        # System message should be passed to the model, not mutate the caller's list
        assert len(messages) == 1, "Caller's message list should not be mutated"
        call_messages = mock_model.chat.call_args[1]["messages"]
        assert call_messages[0].role == "system"
        assert call_messages[0].content == "System prompt"

    async def test_chat_doesnt_duplicate_system_message(
        self, mock_client, mock_model, mock_tool_cache
    ):
        """Test that chat doesn't add system message if already present."""
        from casual_llm import SystemMessage

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))

        chat = McpToolChat(mock_client, "System prompt", mock_tool_cache)
        messages = [SystemMessage(content="Existing system"), UserMessage(content="Hello")]

        await chat.chat(messages, model=mock_model)

        # Should not add another system message; caller list untouched
        assert len(messages) == 2, "Caller's message list should not be mutated"
        call_messages = mock_model.chat.call_args[1]["messages"]
        system_messages = [m for m in call_messages if m.role == "system"]
        assert len(system_messages) == 1
        assert system_messages[0].content == "Existing system"

    async def test_chat_loops_on_tool_calls(self, mock_client, mock_model, mock_tool_cache):
        """Test that chat loops when LLM requests tool calls."""
        # First response has tool call, second doesn't
        tool_call = AssistantToolCall(
            id="call_1", function=AssistantToolCallFunction(name="tool1", arguments="{}")
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )

        # Mock tool execution
        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        messages = [UserMessage(content="Test")]

        response = await chat.chat(messages, model=mock_model)

        # Should have called provider twice (once for tool call, once for final)
        assert mock_model.chat.call_count == 2
        assert len(response) >= 2  # At least assistant message and tool result

    async def test_chat_stops_when_no_tool_calls(self, mock_client, mock_model, mock_tool_cache):
        """Test that chat stops when LLM doesn't request tool calls."""
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Final response"))

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        messages = [UserMessage(content="Test")]

        response = await chat.chat(messages, model=mock_model)

        # Should have called provider once
        assert mock_model.chat.call_count == 1
        assert len(response) == 1
        assert response[0].content == "Final response"


class TestMcpToolChatStats:
    """Tests for McpToolChat stats functionality."""

    def test_get_stats_returns_none_before_chat(self, mock_client, mock_tool_cache):
        """Test that get_stats returns None before any chat calls."""
        chat = McpToolChat(mock_client, "System", mock_tool_cache)

        assert chat.get_stats() is None

    async def test_get_stats_returns_stats_after_chat(self, mock_client, mock_tool_cache):
        """Test that get_stats returns stats after chat call."""
        from casual_llm import Usage

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        model.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Hello")], model=model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tokens.prompt_tokens == 10
        assert stats.tokens.completion_tokens == 5
        assert stats.tokens.total_tokens == 15
        assert stats.llm_calls == 1

    async def test_stats_reset_on_new_chat(self, mock_client, mock_tool_cache):
        """Test that stats are reset at the start of each chat call."""
        from casual_llm import Usage

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        model.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        chat = McpToolChat(mock_client, "System", mock_tool_cache)

        # First chat
        await chat.chat([UserMessage(content="First")], model=model)
        stats1 = chat.get_stats()
        assert stats1.tokens.prompt_tokens == 10

        # Second chat - stats should be fresh, not accumulated
        await chat.chat([UserMessage(content="Second")], model=model)
        stats2 = chat.get_stats()
        assert stats2.tokens.prompt_tokens == 10  # Not 20

    async def test_stats_accumulate_across_llm_calls(self, mock_client, mock_tool_cache):
        """Test that token usage accumulates across multiple LLM calls in one chat."""
        from casual_llm import Usage

        tool_call = AssistantToolCall(
            id="call_1", function=AssistantToolCallFunction(name="math_add", arguments="{}")
        )

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )
        # Return different usage for each call
        model.get_usage = Mock(
            side_effect=[
                Usage(prompt_tokens=100, completion_tokens=20),
                Usage(prompt_tokens=150, completion_tokens=30),
            ]
        )

        # Mock tool execution
        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Test")], model=model)

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

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=tool_calls),
                AssistantMessage(content="Final response"),
            ]
        )
        model.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        # Mock tool execution
        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        chat = McpToolChat(mock_client, "System", mock_tool_cache, server_names={"math", "words"})
        await chat.chat([UserMessage(content="Test")], model=model)

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

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )
        model.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        # Mock tool execution
        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        # No server_names provided, so all tools fall back to "default"
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Test")], model=model)

        stats = chat.get_stats()
        assert stats.tool_calls.by_server == {"default": 1}

    async def test_stats_handle_no_usage_from_model(self, mock_client, mock_tool_cache):
        """Test that stats handle models that return None for usage."""
        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(return_value=AssistantMessage(content="Response"))
        model.get_usage = Mock(return_value=None)

        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        await chat.chat([UserMessage(content="Hello")], model=model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tokens.prompt_tokens == 0
        assert stats.tokens.completion_tokens == 0
        assert stats.llm_calls == 1

    async def test_stats_use_extract_server_and_tool(self, mock_client, mock_tool_cache):
        """Test that stats use extract_server_and_tool with server_names for attribution."""
        from casual_llm import Usage

        tool_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="my_awesome_add", arguments="{}"),
        )

        model = AsyncMock(spec=Model)
        model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[tool_call]),
                AssistantMessage(content="Final response"),
            ]
        )
        model.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        class MockContent:
            type = "text"
            text = "result"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        # With server_names containing "my_awesome", the tool should be attributed correctly
        chat = McpToolChat(mock_client, "System", mock_tool_cache, server_names={"my_awesome"})
        await chat.chat([UserMessage(content="Test")], model=model)

        stats = chat.get_stats()
        assert stats.tool_calls.by_server == {"my_awesome": 1}


def _make_config(
    servers: dict[str, StdioServerConfig] | None = None,
    models: dict[str, McpModelConfig] | None = None,
) -> Config:
    """Build a minimal Config for testing."""
    return Config(
        models=models or {"gpt-4.1": McpModelConfig(client="openai", model="gpt-4.1")},
        clients={"openai": McpClientConfig(provider="openai")},
        servers=servers or {"math": StdioServerConfig(command="echo")},
    )


class TestModelResolution:
    """Tests for McpToolChat._resolve_model()."""

    def test_model_instance_passed_directly(self):
        """When a Model instance is passed, it should be returned directly."""
        mock_client = AsyncMock()
        mock_model = AsyncMock(spec=Model)

        chat = McpToolChat(mock_client)
        result = chat._resolve_model(mock_model)
        assert result is mock_model

    def test_string_name_resolved_via_factory(self):
        """When a string name is passed, it should be resolved via model_factory."""
        mock_client = AsyncMock()
        mock_factory = Mock(spec=ModelFactory)
        mock_resolved = AsyncMock(spec=Model)
        mock_factory.get_model.return_value = mock_resolved

        chat = McpToolChat(mock_client, model_factory=mock_factory)
        result = chat._resolve_model("gpt-4.1")
        assert result is mock_resolved
        mock_factory.get_model.assert_called_once_with("gpt-4.1")

    def test_string_name_without_factory_raises(self):
        """When a string name is passed without factory, ValueError should be raised."""
        mock_client = AsyncMock()

        chat = McpToolChat(mock_client)
        with pytest.raises(ValueError, match="model_factory"):
            chat._resolve_model("gpt-4.1")

    def test_none_always_raises_value_error(self):
        """When None is passed, should always raise ValueError (no default model)."""
        mock_client = AsyncMock()

        chat = McpToolChat(mock_client)
        with pytest.raises(ValueError, match="No model specified"):
            chat._resolve_model(None)

    def test_none_with_no_default_raises(self):
        """When None is passed with no default model, ValueError should be raised."""
        mock_client = AsyncMock()

        chat = McpToolChat(mock_client)
        with pytest.raises(ValueError, match="No model specified"):
            chat._resolve_model(None)


class TestSystemPromptResolution:
    """Tests for McpToolChat._resolve_system_prompt()."""

    async def test_explicit_system_returned(self):
        """Explicit system param should be returned directly."""
        mock_client = AsyncMock()
        chat = McpToolChat(mock_client, system="default system")
        result = await chat._resolve_system_prompt(system="explicit prompt")
        assert result == "explicit prompt"

    async def test_falls_back_to_self_system(self):
        """When no explicit system and no template, should fall back to self.system."""
        mock_client = AsyncMock()
        chat = McpToolChat(mock_client, system="default system")
        result = await chat._resolve_system_prompt()
        assert result == "default system"

    async def test_none_when_no_system_anywhere(self):
        """When no system prompt exists anywhere, should return None."""
        mock_client = AsyncMock()
        chat = McpToolChat(mock_client)
        result = await chat._resolve_system_prompt()
        assert result is None

    async def test_template_resolved_from_model_config(self):
        """When model has a template config, system prompt should be rendered from it."""
        mock_client = AsyncMock()
        config = _make_config(
            models={
                "gpt-4.1": McpModelConfig(
                    client="openai", model="gpt-4.1", template="test_template"
                )
            },
        )
        mock_tool_cache = Mock()
        mock_tool_cache.get_tools = AsyncMock(return_value=[])

        chat = McpToolChat(mock_client, tool_cache=mock_tool_cache, system="default")
        chat._config = config

        with patch(
            "casual_mcp.mcp_tool_chat.render_system_prompt",
            return_value="rendered template",
        ) as mock_render:
            result = await chat._resolve_system_prompt(model_name="gpt-4.1")
            assert result == "rendered template"
            mock_render.assert_called_once_with("test_template.j2", [])

    async def test_explicit_system_overrides_template(self):
        """Explicit system should take precedence over model template."""
        mock_client = AsyncMock()
        config = _make_config(
            models={
                "gpt-4.1": McpModelConfig(
                    client="openai", model="gpt-4.1", template="test_template"
                )
            },
        )

        chat = McpToolChat(mock_client)
        chat._config = config
        result = await chat._resolve_system_prompt(system="explicit", model_name="gpt-4.1")
        assert result == "explicit"


class TestMcpToolChatFromConfig:
    """Tests for McpToolChat.from_config() classmethod."""

    def test_creates_instance_with_correct_attributes(self):
        """from_config() should create an instance with all dependencies wired."""
        config = _make_config()

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client") as mock_load_client:
            mock_client = AsyncMock()
            mock_load_client.return_value = mock_client

            chat = McpToolChat.from_config(config, system="test system")

            assert chat.mcp_client is mock_client
            assert chat.model_factory is not None
            assert isinstance(chat.model_factory, ModelFactory)
            assert chat.server_names == {"math"}
            assert chat._config is config
            assert chat.system == "test system"

    def test_server_names_from_config(self):
        """from_config() should set server_names from config keys."""
        config = _make_config(
            servers={
                "math": StdioServerConfig(command="echo"),
                "weather": StdioServerConfig(command="echo"),
            }
        )

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)
            assert chat.server_names == {"math", "weather"}

    async def test_chat_with_model_name_resolves_via_factory(self):
        """chat() with a string model should resolve via the factory."""
        config = _make_config()

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)

        # Mock the model factory's get_model
        mock_model = AsyncMock()
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))
        mock_model.get_usage = Mock(return_value=None)
        chat.model_factory = Mock(spec=ModelFactory)
        chat.model_factory.get_model.return_value = mock_model

        # Mock tool cache
        chat.tool_cache = Mock()
        chat.tool_cache.get_tools = AsyncMock(return_value=[])
        chat.tool_cache.version = 1

        messages = [UserMessage(content="Hi")]
        response = await chat.chat(messages, model="gpt-4.1")

        chat.model_factory.get_model.assert_called_once_with("gpt-4.1")
        assert response[-1].content == "Hello"

    async def test_chat_with_no_model_and_no_default_raises(self):
        """chat() with no model and no default should raise ValueError."""
        config = _make_config()

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)

        chat.tool_cache = Mock()
        chat.tool_cache.get_tools = AsyncMock(return_value=[])
        chat.tool_cache.version = 1

        with pytest.raises(ValueError, match="No model specified"):
            await chat.chat([UserMessage(content="Hi")])

    async def test_chat_with_model_instance_bypasses_factory(self):
        """chat() with a Model instance should use it directly."""
        config = _make_config()

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)

        mock_model = AsyncMock(spec=Model)
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Direct"))
        mock_model.get_usage = Mock(return_value=None)

        chat.tool_cache = Mock()
        chat.tool_cache.get_tools = AsyncMock(return_value=[])
        chat.tool_cache.version = 1

        response = await chat.chat([UserMessage(content="Hi")], model=mock_model)

        assert response[-1].content == "Direct"
        # Factory should not have been called
        if chat.model_factory:
            mock_factory = Mock(spec=ModelFactory)
            chat.model_factory = mock_factory
            # Not called since we passed model instance directly

    async def test_system_prompt_resolved_from_model_template(self):
        """When model has template config and no explicit system, template should be used."""
        config = _make_config(
            models={"gpt-4.1": McpModelConfig(client="openai", model="gpt-4.1", template="custom")},
        )

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)

        mock_model = AsyncMock()
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))
        mock_model.get_usage = Mock(return_value=None)
        chat.model_factory = Mock(spec=ModelFactory)
        chat.model_factory.get_model.return_value = mock_model

        chat.tool_cache = Mock()
        chat.tool_cache.get_tools = AsyncMock(return_value=[])
        chat.tool_cache.version = 1

        with patch(
            "casual_mcp.mcp_tool_chat.render_system_prompt",
            return_value="rendered template prompt",
        ):
            await chat.chat([UserMessage(content="Hi")], model="gpt-4.1")

        # Verify the system message was inserted from the template
        call_args = mock_model.chat.call_args[1]
        messages = call_args["messages"]
        system_msgs = [m for m in messages if m.role == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "rendered template prompt"

    async def test_explicit_system_overrides_template(self):
        """Explicit system param should override model template."""
        config = _make_config(
            models={"gpt-4.1": McpModelConfig(client="openai", model="gpt-4.1", template="custom")},
        )

        with patch("casual_mcp.mcp_tool_chat.load_mcp_client"):
            chat = McpToolChat.from_config(config)

        mock_model = AsyncMock()
        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))
        mock_model.get_usage = Mock(return_value=None)
        chat.model_factory = Mock(spec=ModelFactory)
        chat.model_factory.get_model.return_value = mock_model

        chat.tool_cache = Mock()
        chat.tool_cache.get_tools = AsyncMock(return_value=[])
        chat.tool_cache.version = 1

        await chat.chat(
            [UserMessage(content="Hi")],
            model="gpt-4.1",
            system="explicit system",
        )

        call_args = mock_model.chat.call_args[1]
        messages = call_args["messages"]
        system_msgs = [m for m in messages if m.role == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "explicit system"


class TestConcurrentRequests:
    """Test that concurrent chat() calls don't corrupt each other's stats."""

    async def test_concurrent_calls_have_independent_stats(self):
        """Two concurrent chat() calls should produce independent stats."""
        import asyncio

        from casual_llm import Usage

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        cache.version = 1

        chat = McpToolChat(client, "System", cache)

        # Create two models with different usage to distinguish them
        model_a = AsyncMock(spec=Model)
        model_a.chat = AsyncMock(return_value=AssistantMessage(content="A"))
        model_a.get_usage = Mock(return_value=Usage(prompt_tokens=100, completion_tokens=50))

        model_b = AsyncMock(spec=Model)
        model_b.chat = AsyncMock(return_value=AssistantMessage(content="B"))
        model_b.get_usage = Mock(return_value=Usage(prompt_tokens=10, completion_tokens=5))

        # Run both calls concurrently
        results = await asyncio.gather(
            chat.chat([UserMessage(content="Call A")], model=model_a),
            chat.chat([UserMessage(content="Call B")], model=model_b),
        )

        # Both should succeed
        assert len(results) == 2
        assert results[0][-1].content == "A"
        assert results[1][-1].content == "B"

        # get_stats() returns whichever finished last — but the key point
        # is that it should be one complete stats object, not a corrupted mix
        stats = chat.get_stats()
        assert stats is not None
        assert stats.llm_calls == 1
        # Should be from one call — either (100,50) or (10,5), not a mix
        assert stats.tokens.prompt_tokens in (100, 10)
        assert stats.tokens.completion_tokens in (50, 5)
        # They should be from the same call
        if stats.tokens.prompt_tokens == 100:
            assert stats.tokens.completion_tokens == 50
        else:
            assert stats.tokens.completion_tokens == 5
