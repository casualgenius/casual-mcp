"""Tests for tool discovery integration in McpToolChat.

Covers:
- partition_tools helper
- McpToolChat configuration acceptance
- Full chat loop with tool discovery (search-tools injected/not injected)
- Tool discovered via search-tools and subsequently used
- Deferred tool called without search returns error
- Multiple search calls expanding the tool set
- Tool cache version change triggers rebuild
- Toolset filtering respected for deferred tools
- Stats tracking for search-tools calls
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, PropertyMock

import mcp
import pytest
from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolCallFunction,
    Model,
    Tool,
    UserMessage,
)

from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.models.config import Config, McpClientConfig, McpModelConfig
from casual_mcp.models.mcp_server_config import RemoteServerConfig, StdioServerConfig
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig
from casual_mcp.models.toolset_config import ToolSetConfig
from casual_mcp.synthetic_tool import SyntheticToolResult
from casual_mcp.tool_discovery import build_tool_server_map, partition_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, description: str) -> mcp.Tool:
    return mcp.Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": {}},
    )


def _make_config(
    servers: dict[str, Any] | None = None,
    discovery: ToolDiscoveryConfig | None = None,
) -> Config:
    """Build a minimal Config for testing."""
    server_configs: dict[str, StdioServerConfig | RemoteServerConfig] = {}
    if servers:
        for name, cfg in servers.items():
            if isinstance(cfg, (StdioServerConfig, RemoteServerConfig)):
                server_configs[name] = cfg
            else:
                server_configs[name] = StdioServerConfig(
                    command="echo",
                    defer_loading=cfg.get("defer_loading", False),
                )
    return Config(
        models={"test": McpModelConfig(client="test", model="test-model")},
        clients={"test": McpClientConfig(provider="openai")},
        servers=server_configs,
        tool_discovery=discovery,
    )


# ---------------------------------------------------------------------------
# partition_tools tests
# ---------------------------------------------------------------------------


class TestPartitionTools:
    """Tests for the partition_tools helper."""

    def test_no_discovery_config_returns_all_loaded(self) -> None:
        """When discovery is not configured, all tools are loaded."""
        tools = [_make_tool("math_add", "Add"), _make_tool("weather_get", "Get weather")]
        config = _make_config(
            servers={"math": {"defer_loading": False}, "weather": {"defer_loading": True}}
        )
        # No tool_discovery set -> None
        loaded, deferred = partition_tools(tools, config, {"math", "weather"})
        assert len(loaded) == 2
        assert deferred == {}

    def test_discovery_disabled_returns_all_loaded(self) -> None:
        """When discovery.enabled is False, all tools are loaded."""
        tools = [_make_tool("math_add", "Add")]
        config = _make_config(
            servers={"math": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=False),
        )
        loaded, deferred = partition_tools(tools, config, {"math"})
        assert len(loaded) == 1
        assert deferred == {}

    def test_partition_by_server_defer_loading(self) -> None:
        """Tools from defer_loading servers go to deferred set."""
        tools = [
            _make_tool("math_add", "Add"),
            _make_tool("weather_get", "Get weather"),
        ]
        config = _make_config(
            servers={"math": {"defer_loading": False}, "weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )
        loaded, deferred = partition_tools(tools, config, {"math", "weather"})
        assert len(loaded) == 1
        assert loaded[0].name == "math_add"
        assert "weather" in deferred
        assert len(deferred["weather"]) == 1
        assert deferred["weather"][0].name == "weather_get"

    def test_defer_all_overrides_per_server(self) -> None:
        """When defer_all is True, all servers are deferred regardless."""
        tools = [
            _make_tool("math_add", "Add"),
            _make_tool("weather_get", "Get weather"),
        ]
        config = _make_config(
            servers={"math": {"defer_loading": False}, "weather": {"defer_loading": False}},
            discovery=ToolDiscoveryConfig(enabled=True, defer_all=True),
        )
        loaded, deferred = partition_tools(tools, config, {"math", "weather"})
        assert len(loaded) == 0
        assert "math" in deferred
        assert "weather" in deferred

    def test_unknown_server_loaded_eagerly(self) -> None:
        """Tools from servers not in config are loaded eagerly."""
        tools = [_make_tool("unknown_tool", "Unknown")]
        config = _make_config(
            servers={},
            discovery=ToolDiscoveryConfig(enabled=True),
        )
        loaded, deferred = partition_tools(tools, config, set())
        assert len(loaded) == 1
        assert deferred == {}

    def test_no_deferred_tools(self) -> None:
        """When all servers have defer_loading=False, no tools are deferred."""
        tools = [_make_tool("math_add", "Add")]
        config = _make_config(
            servers={"math": {"defer_loading": False}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )
        loaded, deferred = partition_tools(tools, config, {"math"})
        assert len(loaded) == 1
        assert deferred == {}


class TestBuildToolServerMap:
    """Tests for build_tool_server_map helper."""

    def test_builds_correct_mapping(self) -> None:
        tools = [_make_tool("math_add", "Add"), _make_tool("weather_get", "Get")]
        mapping = build_tool_server_map(tools, {"math", "weather"})
        assert mapping["math_add"] == "math"
        assert mapping["weather_get"] == "weather"

    def test_single_server(self) -> None:
        tools = [_make_tool("add", "Add")]
        mapping = build_tool_server_map(tools, {"math"})
        assert mapping["add"] == "math"


# ---------------------------------------------------------------------------
# McpToolChat configuration tests
# ---------------------------------------------------------------------------


class TestMcpToolChatDiscoveryConfig:
    """Tests for McpToolChat accepting tool discovery configuration."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    @pytest.fixture
    def mock_tool_cache(self) -> Mock:
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=[])
        cache.version = 1
        return cache

    def test_accepts_config_param(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """McpToolChat accepts config set on instance."""
        config = _make_config(
            servers={"math": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        assert chat._config is config
        assert chat._tool_discovery_config is not None
        assert chat._tool_discovery_config.enabled is True

    def test_accepts_explicit_discovery_config(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Explicit tool_discovery_config overrides config.tool_discovery."""
        config = _make_config(
            discovery=ToolDiscoveryConfig(enabled=False),
        )
        override = ToolDiscoveryConfig(enabled=True, max_search_results=10)
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        chat._config = config
        chat._tool_discovery_config = override
        assert chat._tool_discovery_config is override
        assert chat._tool_discovery_config.enabled is True

    def test_no_config_disables_discovery(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """Without config, discovery is disabled."""
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        assert not chat._is_discovery_enabled()

    def test_backward_compatible_without_new_params(
        self, mock_client: AsyncMock, mock_model: AsyncMock, mock_tool_cache: Mock
    ) -> None:
        """McpToolChat still works without config or tool_discovery_config."""
        chat = McpToolChat(mock_client, "System", mock_tool_cache)
        assert chat._config is None
        assert chat._tool_discovery_config is None


# ---------------------------------------------------------------------------
# Integration tests: full chat loop with tool discovery
# ---------------------------------------------------------------------------


class TestChatLoopWithDiscovery:
    """Integration tests for the chat loop with tool discovery enabled."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    def _make_tool_cache(
        self,
        tools: list[mcp.Tool],
        version: int = 1,
    ) -> Mock:
        """Build a mock tool cache with specified tools."""
        cache = Mock()
        cache.get_tools = AsyncMock(return_value=tools)
        type(cache).version = PropertyMock(return_value=version)
        return cache

    def _make_chat_with_discovery(
        self,
        mock_client: AsyncMock,
        mock_model: AsyncMock,
        all_tools: list[mcp.Tool],
        server_names: set[str],
        servers: dict[str, Any],
        discovery: ToolDiscoveryConfig | None = None,
        cache_version: int = 1,
    ) -> McpToolChat:
        """Build McpToolChat with tool discovery enabled."""
        config = _make_config(
            servers=servers,
            discovery=discovery or ToolDiscoveryConfig(enabled=True),
        )
        tool_cache = self._make_tool_cache(all_tools, version=cache_version)
        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names=server_names,
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        return chat

    async def test_search_tools_injected_when_deferred_exist(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """search-tools should be injected when deferred tools exist."""
        tools = [
            _make_tool("math_add", "Add two numbers"),
            _make_tool("weather_get", "Get weather"),
        ]

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = self._make_chat_with_discovery(
            mock_client,
            mock_model,
            tools,
            {"math", "weather"},
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        # Check that the model was called with search-tools in the tool list
        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" in tool_names
        assert "math_add" in tool_names
        # weather_get should NOT be in the tool list (it's deferred)
        assert "weather_get" not in tool_names

    async def test_search_tools_not_injected_when_no_deferred(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """search-tools should NOT be injected when all tools are loaded."""
        tools = [_make_tool("math_add", "Add")]

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = self._make_chat_with_discovery(
            mock_client,
            mock_model,
            tools,
            {"math"},
            servers={"math": {"defer_loading": False}},
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" not in tool_names
        assert "math_add" in tool_names

    async def test_search_tools_not_injected_when_discovery_disabled(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """search-tools should NOT be injected when discovery is disabled."""
        tools = [_make_tool("weather_get", "Get weather")]

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = self._make_chat_with_discovery(
            mock_client,
            mock_model,
            tools,
            {"weather"},
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=False),
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" not in tool_names
        # All tools should be loaded (discovery disabled)
        assert "weather_get" in tool_names

    async def test_discovery_system_message_injected_when_deferred_exist(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """A system message with the manifest should be injected for deferred tools."""
        tools = [
            _make_tool("math_add", "Add two numbers"),
            _make_tool("weather_get", "Get weather"),
        ]

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = self._make_chat_with_discovery(
            mock_client,
            mock_model,
            tools,
            {"math", "weather"},
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        call_kwargs = mock_model.chat.call_args[1]
        system_messages = [m for m in call_kwargs["messages"] if m.role == "system"]
        # Should have the default system prompt AND the discovery manifest
        assert len(system_messages) == 2
        discovery_msg = system_messages[1]
        assert "search-tools" in discovery_msg.content
        assert "weather" in discovery_msg.content

    async def test_no_discovery_system_message_when_no_deferred(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """No discovery system message when all tools are loaded."""
        tools = [_make_tool("math_add", "Add")]

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = self._make_chat_with_discovery(
            mock_client,
            mock_model,
            tools,
            {"math"},
            servers={"math": {"defer_loading": False}},
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        call_kwargs = mock_model.chat.call_args[1]
        system_messages = [m for m in call_kwargs["messages"] if m.role == "system"]
        # Only the default system prompt, no discovery message
        assert len(system_messages) == 1
        assert "search-tools" not in system_messages[0].content


class TestDiscoverAndUseFlow:
    """Tests for the discover-then-use flow."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_discover_tool_then_use_it(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """LLM searches for a tool, discovers it, then calls it successfully."""
        # Set up tools: math is eager, weather is deferred
        math_tool = _make_tool("math_add", "Add two numbers together")
        weather_tool = _make_tool("weather_get_forecast", "Get weather forecast")
        all_tools = [math_tool, weather_tool]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=all_tools)
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Step 1: LLM calls search-tools to find weather tool
        search_call = AssistantToolCall(
            id="call_search",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "weather forecast"}',
            ),
        )

        # Step 2: LLM calls the discovered weather tool
        weather_call = AssistantToolCall(
            id="call_weather",
            function=AssistantToolCallFunction(
                name="weather_get_forecast",
                arguments="{}",
            ),
        )

        # Mock MCP tool execution for weather tool
        class MockContent:
            type = "text"
            text = '{"temperature": 72}'

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        # Model responses:
        # 1st call: LLM calls search-tools
        # 2nd call: LLM calls weather_get_forecast (now loaded)
        # 3rd call: LLM gives final answer
        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="", tool_calls=[weather_call]),
                AssistantMessage(content="The temperature is 72 degrees."),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math", "weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        response = await chat.chat([UserMessage(content="What's the weather?")], model=mock_model)

        # Verify the flow:
        # msg 0: assistant with search-tools call
        # msg 1: tool result from search-tools
        # msg 2: assistant with weather_get_forecast call
        # msg 3: tool result from weather_get_forecast
        # msg 4: final assistant message
        assert len(response) == 5
        assert response[0].tool_calls is not None
        assert response[0].tool_calls[0].function.name == "search-tools"
        assert "Found" in response[1].content
        assert response[2].tool_calls is not None
        assert response[2].tool_calls[0].function.name == "weather_get_forecast"
        assert response[4].content == "The temperature is 72 degrees."

        # The weather tool should have been called via MCP
        mock_client.call_tool.assert_called_once()

        # After search, the second model.chat call should include weather_get_forecast
        second_call_tools = mock_model.chat.call_args_list[1][1]["options"].tools
        second_call_tool_names = {t.name for t in second_call_tools}
        assert "weather_get_forecast" in second_call_tool_names
        assert "math_add" in second_call_tool_names
        assert "search-tools" in second_call_tool_names

    async def test_multiple_search_calls_expand_tool_set(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Multiple search-tools calls should progressively expand the loaded set."""
        weather_tool = _make_tool("weather_get_forecast", "Get weather forecast")
        weather_current = _make_tool("weather_get_current", "Get current conditions")
        all_tools = [weather_tool, weather_current]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=all_tools)
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # First search: find forecast
        search_call_1 = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "forecast"}',
            ),
        )
        # Second search: find current
        search_call_2 = AssistantToolCall(
            id="call_s2",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "current conditions"}',
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call_1]),
                AssistantMessage(content="", tool_calls=[search_call_2]),
                AssistantMessage(content="Done"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        await chat.chat([UserMessage(content="Test")], model=mock_model)

        # After first search, forecast should be loaded
        second_call_tools = mock_model.chat.call_args_list[1][1]["options"].tools
        second_tool_names = {t.name for t in second_call_tools}
        assert "weather_get_forecast" in second_tool_names

        # After second search, current should also be loaded
        third_call_tools = mock_model.chat.call_args_list[2][1]["options"].tools
        third_tool_names = {t.name for t in third_call_tools}
        assert "weather_get_forecast" in third_tool_names
        assert "weather_get_current" in third_tool_names

        # Stats should show 2 search-tools calls
        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool.get("search-tools", 0) == 2


class TestDeferredToolWithoutSearch:
    """Tests for calling a deferred tool without using search-tools first."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_deferred_tool_returns_error(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Calling a deferred tool without search should return an error message."""
        weather_tool = _make_tool("weather_get_forecast", "Get weather forecast")
        all_tools = [weather_tool]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=all_tools)
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # LLM tries to call the deferred tool directly
        direct_call = AssistantToolCall(
            id="call_direct",
            function=AssistantToolCallFunction(
                name="weather_get_forecast",
                arguments="{}",
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[direct_call]),
                AssistantMessage(content="I'll use search-tools first."),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        response = await chat.chat([UserMessage(content="Get weather")], model=mock_model)

        # The tool result should be an error
        tool_result = response[1]
        assert "not yet loaded" in tool_result.content
        assert "search-tools" in tool_result.content
        assert tool_result.name == "weather_get_forecast"

        # MCP client should NOT have been called
        mock_client.call_tool.assert_not_called()

    async def test_deferred_tool_error_not_forwarded_to_mcp(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Deferred tool call should NOT be forwarded to MCP client."""
        weather_tool = _make_tool("weather_get", "Get weather")
        all_tools = [weather_tool]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=all_tools)
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="weather_get", arguments="{}"),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[call]),
                AssistantMessage(content="OK"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        mock_client.call_tool.assert_not_called()


class TestToolCacheVersionChange:
    """Tests for tool cache version change handling."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_version_change_rebuilds_index_keeps_loaded(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Cache version change should rebuild the index but keep previously loaded tools.

        Flow:
        1. Initial tools: math_add (loaded), weather_get (deferred)
        2. LLM searches for weather_get -> it becomes loaded
        3. Version bumps (new tool weather_alert appears)
        4. LLM makes another call -> rebuild happens
        5. Verify: math_add + weather_get (kept from prior discovery) + search-tools
           present, weather_alert still deferred
        """
        weather_tool = _make_tool("weather_get", "Get weather")
        math_tool = _make_tool("math_add", "Add numbers")
        new_tool = _make_tool("weather_alert", "Weather alerts")

        # Initial tools: weather deferred, math loaded
        initial_tools = [weather_tool, math_tool]
        # After version bump: adds a new weather tool
        updated_tools = [weather_tool, math_tool, new_tool]

        version_counter = [1]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(side_effect=[initial_tools, updated_tools])

        def get_version() -> int:
            return version_counter[0]

        type(tool_cache).version = PropertyMock(side_effect=get_version)

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Step 1: LLM searches and loads weather_get
        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"tool_names": ["weather_get"]}',
            ),
        )

        call_count = [0]

        async def model_chat_with_version_bump(**kwargs: Any) -> AssistantMessage:
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: LLM calls search-tools to load weather_get
                return AssistantMessage(content="", tool_calls=[search_call])
            elif call_count[0] == 2:
                # Second call: after search result returned
                # Bump version to simulate cache refresh
                version_counter[0] = 2
                # LLM wants to keep going (version change detected on next iteration)
                return AssistantMessage(
                    content="",
                    tool_calls=[
                        AssistantToolCall(
                            id="call_s2",
                            function=AssistantToolCallFunction(
                                name="search-tools",
                                arguments='{"query": "alert"}',
                            ),
                        )
                    ],
                )
            else:
                return AssistantMessage(content="Done")

        mock_model.chat = AsyncMock(side_effect=model_chat_with_version_bump)

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math", "weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        response = await chat.chat([UserMessage(content="Test")], model=mock_model)

        # Verify the flow produced expected messages:
        # msg 0: assistant with search-tools call
        # msg 1: tool result from search-tools (Found weather_get)
        # msg 2: assistant with second search-tools call (version bumped here)
        # msg 3: tool result from second search-tools (Found weather_alert)
        # msg 4: final assistant message
        assert len(response) == 5

        # After version change rebuild, the third model.chat call should include:
        # - math_add (always loaded)
        # - weather_get (previously discovered, kept across rebuild)
        # - search-tools (weather_alert is still deferred)
        # - weather_alert should NOT be in tool list (still deferred)
        third_call_tools = mock_model.chat.call_args_list[2][1]["options"].tools
        third_call_names = {t.name for t in third_call_tools}
        assert "math_add" in third_call_names, "Eagerly loaded tool should survive rebuild"
        assert "weather_get" in third_call_names, (
            "Previously discovered tool should be preserved across rebuild"
        )
        assert "search-tools" in third_call_names, (
            "search-tools should be re-injected when new deferred tools exist"
        )

    async def test_version_change_removes_search_tools_when_no_deferred_remain(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """After version change, if no deferred tools remain, search-tools is removed."""
        weather_tool = _make_tool("weather_get", "Get weather")

        # Initial: weather deferred. After version bump: same tools but server
        # no longer defers (simulated via empty deferred partition).
        initial_tools = [weather_tool]
        # The rebuild re-fetches and re-partitions. If the server config
        # no longer defers, all tools go to loaded and search-tools is removed.
        # We simulate this by having the config NOT defer on rebuild.
        # Since we can't change config mid-call, we instead just ensure that
        # after loading weather_get via search, a rebuild with the same tools
        # keeps weather_get loaded but re-creates search-tools only if needed.

        version_counter = [1]
        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(side_effect=[initial_tools, initial_tools])

        def get_version() -> int:
            return version_counter[0]

        type(tool_cache).version = PropertyMock(side_effect=get_version)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # LLM loads weather_get via search, then version bumps on next iteration
        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"tool_names": ["weather_get"]}',
            ),
        )

        call_count = [0]

        async def model_chat_fn(**kwargs: Any) -> AssistantMessage:
            call_count[0] += 1
            if call_count[0] == 1:
                return AssistantMessage(content="", tool_calls=[search_call])
            elif call_count[0] == 2:
                # Bump version to trigger rebuild
                version_counter[0] = 2
                return AssistantMessage(content="Done")
            return AssistantMessage(content="Done")

        mock_model.chat = AsyncMock(side_effect=model_chat_fn)

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        await chat.chat([UserMessage(content="Test")], model=mock_model)

        # After search, weather_get was loaded. On rebuild with same tools,
        # weather_get is now in previously_loaded_names and will be kept in loaded.
        # Since it was the only deferred tool, no deferred remain -> search-tools removed.
        # The second call (call_count=2) should show weather_get but no search-tools
        second_call_tools = mock_model.chat.call_args_list[1][1]["options"].tools
        second_call_names = {t.name for t in second_call_tools}
        assert "weather_get" in second_call_names
        assert "search-tools" in second_call_names  # Still present before rebuild


class TestToolsetFilteringWithDiscovery:
    """Tests that toolset filtering is respected with tool discovery."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_toolset_filtering_excludes_from_deferred(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Tools excluded by toolset should not appear in deferred set."""
        math_tool = _make_tool("math_add", "Add")
        weather_tool = _make_tool("weather_get", "Get weather")
        all_tools = [math_tool, weather_tool]

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=all_tools)
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Toolset that only includes math server
        tool_set = ToolSetConfig(servers={"math": True})

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math", "weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], tool_set=tool_set, model=mock_model)

        # Only math_add should be in tools (weather excluded by toolset)
        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "math_add" in tool_names
        # search-tools should NOT be present (no deferred tools after filtering)
        assert "search-tools" not in tool_names
        # weather_get should not be present
        assert "weather_get" not in tool_names


class TestStatsTrackingWithDiscovery:
    """Tests for stats tracking with tool discovery."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_search_tools_tracked_under_synthetic(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """search-tools calls should be tracked under _synthetic server."""
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "weather"}',
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="Done"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool.get("search-tools") == 1
        assert stats.tool_calls.by_server.get("_synthetic") == 1

    async def test_discovered_tool_stats_tracked_correctly(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Tools discovered via search-tools should track stats under their actual server."""
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # First: search for weather tool
        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"tool_names": ["weather_get"]}',
            ),
        )
        # Then: use the discovered weather tool
        weather_call = AssistantToolCall(
            id="call_w1",
            function=AssistantToolCallFunction(
                name="weather_get",
                arguments="{}",
            ),
        )

        class MockContent:
            type = "text"
            text = "Sunny"

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="", tool_calls=[weather_call]),
                AssistantMessage(content="Done"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.tool_calls.by_tool.get("search-tools") == 1
        assert stats.tool_calls.by_tool.get("weather_get") == 1
        assert stats.tool_calls.by_server.get("_synthetic") == 1
        assert stats.tool_calls.by_server.get("weather") == 1

    async def test_deferred_tool_error_still_tracked(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Stats for deferred-tool-called-without-search should be tracked."""
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        direct_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="weather_get", arguments="{}"),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[direct_call]),
                AssistantMessage(content="OK"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        # The deferred tool call should still be tracked
        assert stats.tool_calls.by_tool.get("weather_get") == 1
        assert stats.tool_calls.by_server.get("weather") == 1


class TestDeferAllMode:
    """Tests for defer_all mode."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_defer_all_defers_everything(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """defer_all=True should defer all tools, only search-tools available."""
        math_tool = _make_tool("math_add", "Add numbers")
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[math_tool, weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": False},
            },
            discovery=ToolDiscoveryConfig(enabled=True, defer_all=True),
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math", "weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        # Only search-tools should be in the tool list
        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" in tool_names
        assert "math_add" not in tool_names
        assert "weather_get" not in tool_names


class TestEdgeCases:
    """Edge case and robustness tests for tool discovery integration."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_model(self) -> AsyncMock:
        model = AsyncMock(spec=Model)
        model.get_usage = Mock(return_value=None)
        return model

    async def test_discovery_with_no_tools_at_all(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Discovery should handle an empty tool set gracefully."""
        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"math": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="No tools"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        response = await chat.chat([UserMessage(content="Hi")], model=mock_model)

        # No tools available at all -> no search-tools injected
        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" not in tool_names
        assert len(response) == 1

    async def test_search_returns_no_results(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """search-tools returning no results should not crash or expand tools."""
        weather_tool = _make_tool("weather_get", "Get weather forecast")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # LLM searches for something that doesn't match
        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "zzz_nonexistent_zzz"}',
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="OK"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        response = await chat.chat([UserMessage(content="Test")], model=mock_model)

        # Tool result should mention no tools found
        assert "No tools found" in response[1].content

        # After no results, the second model call should still NOT include
        # weather_get (it was never discovered)
        second_call_tools = mock_model.chat.call_args_list[1][1]["options"].tools
        second_call_names = {t.name for t in second_call_tools}
        assert "weather_get" not in second_call_names
        assert "search-tools" in second_call_names

    async def test_static_synthetic_tools_coexist_with_search_tools(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Static synthetic tools should coexist with search-tools in the registry."""
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Create a static synthetic tool
        static_tool = Mock()
        static_tool.name = "my_custom_tool"
        static_tool.definition = Tool.from_input_schema(
            name="my_custom_tool",
            description="A custom synthetic tool",
            input_schema={"type": "object", "properties": {}},
        )
        static_tool.execute = AsyncMock(
            return_value=SyntheticToolResult(content="custom result", newly_loaded_tools=[])
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
            synthetic_tools=[static_tool],
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        # Both search-tools and my_custom_tool should be available
        call_kwargs = mock_model.chat.call_args[1]
        tool_names = {t.name for t in call_kwargs["options"].tools}
        assert "search-tools" in tool_names
        assert "my_custom_tool" in tool_names
        assert "weather_get" not in tool_names  # deferred

    async def test_deferred_tool_becomes_usable_after_discovery(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """A deferred tool that was initially blocked should work after search-tools loads it."""
        weather_tool = _make_tool("weather_get", "Get weather forecast")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Step 1: LLM tries to call weather_get directly (should get error)
        direct_call = AssistantToolCall(
            id="call_1",
            function=AssistantToolCallFunction(name="weather_get", arguments="{}"),
        )
        # Step 2: LLM searches for weather_get
        search_call = AssistantToolCall(
            id="call_2",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"tool_names": ["weather_get"]}',
            ),
        )
        # Step 3: LLM calls weather_get again (should succeed now)
        retry_call = AssistantToolCall(
            id="call_3",
            function=AssistantToolCallFunction(name="weather_get", arguments="{}"),
        )

        class MockContent:
            type = "text"
            text = '{"temp": 72}'

        mock_client.call_tool = AsyncMock(
            return_value=Mock(content=[MockContent()], structuredContent=None)
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[direct_call]),
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="", tool_calls=[retry_call]),
                AssistantMessage(content="The temperature is 72."),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        response = await chat.chat([UserMessage(content="Get weather")], model=mock_model)

        # msg 0: assistant tries direct call
        # msg 1: error result (not yet loaded)
        # msg 2: assistant calls search-tools
        # msg 3: search-tools result (Found 1 tool)
        # msg 4: assistant retries weather_get
        # msg 5: successful tool result
        # msg 6: final answer
        assert len(response) == 7
        assert "not yet loaded" in response[1].content
        assert "Found" in response[3].content
        # The retry call should succeed via MCP
        mock_client.call_tool.assert_called_once()
        assert response[6].content == "The temperature is 72."

    async def test_llm_calls_count_tracked_with_discovery(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """LLM call count should include all iterations with discovery."""
        weather_tool = _make_tool("weather_get", "Get weather")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        search_call = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "weather"}',
            ),
        )

        mock_model.chat = AsyncMock(
            side_effect=[
                AssistantMessage(content="", tool_calls=[search_call]),
                AssistantMessage(content="Done"),
            ]
        )

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Test")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.llm_calls == 2  # search call + final answer
