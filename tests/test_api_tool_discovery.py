"""Tests for API and CLI integration with tool discovery.

Covers:
- API passes tool discovery config to McpToolChat
- ChatStats includes discovery metrics when applicable
- CLI tools command shows deferred status
- DiscoveryStats model behavior
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import mcp
import pydantic
import pytest
from casual_llm import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolCallFunction,
    Model,
    UserMessage,
)

from casual_mcp.mcp_tool_chat import McpToolChat
from casual_mcp.models.chat_stats import ChatStats, DiscoveryStats
from casual_mcp.models.config import Config, McpClientConfig, McpModelConfig
from casual_mcp.models.mcp_server_config import StdioServerConfig
from casual_mcp.models.tool_discovery_config import ToolDiscoveryConfig

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
    server_configs: dict[str, StdioServerConfig] = {}
    if servers:
        for name, cfg in servers.items():
            if isinstance(cfg, StdioServerConfig):
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
# DiscoveryStats model tests
# ---------------------------------------------------------------------------


class TestDiscoveryStats:
    """Tests for the DiscoveryStats model."""

    def test_defaults(self) -> None:
        """DiscoveryStats should default to zeros."""
        stats = DiscoveryStats()
        assert stats.tools_discovered == 0
        assert stats.search_calls == 0

    def test_mutable(self) -> None:
        """DiscoveryStats fields should be mutable for accumulation."""
        stats = DiscoveryStats()
        stats.search_calls += 3
        stats.tools_discovered += 5
        assert stats.search_calls == 3
        assert stats.tools_discovered == 5

    def test_serialization(self) -> None:
        """DiscoveryStats should serialize correctly."""
        stats = DiscoveryStats(tools_discovered=10, search_calls=2)
        data = stats.model_dump()
        assert data == {"tools_discovered": 10, "search_calls": 2}

    def test_rejects_negative_search_calls(self) -> None:
        """DiscoveryStats should reject negative search_calls."""
        with pytest.raises(pydantic.ValidationError):
            DiscoveryStats(search_calls=-1)

    def test_rejects_negative_tools_discovered(self) -> None:
        """DiscoveryStats should reject negative tools_discovered."""
        with pytest.raises(pydantic.ValidationError):
            DiscoveryStats(tools_discovered=-1)


class TestChatStatsWithDiscovery:
    """Tests for ChatStats with discovery field."""

    def test_discovery_defaults_to_none(self) -> None:
        """ChatStats.discovery should default to None."""
        stats = ChatStats()
        assert stats.discovery is None

    def test_discovery_can_be_set(self) -> None:
        """ChatStats should accept DiscoveryStats."""
        stats = ChatStats(discovery=DiscoveryStats(search_calls=1, tools_discovered=3))
        assert stats.discovery is not None
        assert stats.discovery.search_calls == 1
        assert stats.discovery.tools_discovered == 3

    def test_serialization_without_discovery(self) -> None:
        """Serialization should include discovery=None when not set."""
        stats = ChatStats()
        data = stats.model_dump()
        assert data["discovery"] is None

    def test_serialization_with_discovery(self) -> None:
        """Serialization should include discovery when present."""
        stats = ChatStats(discovery=DiscoveryStats(search_calls=2, tools_discovered=4))
        data = stats.model_dump()
        assert data["discovery"]["search_calls"] == 2
        assert data["discovery"]["tools_discovered"] == 4


# ---------------------------------------------------------------------------
# API: get_chat passes config to McpToolChat
# ---------------------------------------------------------------------------


class TestGetChatPassesConfig:
    """Tests that the API's get_chat() passes config to McpToolChat."""

    @pytest.fixture
    def config_with_discovery(self) -> Config:
        return _make_config(
            servers={"math": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True, max_search_results=10),
        )

    async def test_get_chat_passes_config(self, config_with_discovery: Config) -> None:
        """McpToolChat should receive config when created via get_chat."""
        # Rather than importing main.py (which has module-level side effects),
        # we test the pattern used in get_chat directly.
        mock_client = AsyncMock()
        mock_model = AsyncMock(spec=Model)
        mock_model.get_usage = Mock(return_value=None)
        mock_tool_cache = Mock()
        mock_tool_cache.get_tools = AsyncMock(return_value=[])
        mock_tool_cache.version = 1

        config = config_with_discovery
        chat = McpToolChat(
            mock_client,
            "System prompt",
            tool_cache=mock_tool_cache,
            server_names=set(config.servers.keys()),
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery

        assert chat._config is config
        assert chat._tool_discovery_config is not None
        assert chat._tool_discovery_config.enabled is True
        assert chat._tool_discovery_config.max_search_results == 10

    async def test_get_chat_without_discovery(self) -> None:
        """McpToolChat should work without discovery config."""
        config = _make_config(servers={"math": {"defer_loading": False}})

        mock_client = AsyncMock()
        mock_model = AsyncMock(spec=Model)
        mock_model.get_usage = Mock(return_value=None)
        mock_tool_cache = Mock()
        mock_tool_cache.get_tools = AsyncMock(return_value=[])
        mock_tool_cache.version = 1

        chat = McpToolChat(
            mock_client,
            "System prompt",
            tool_cache=mock_tool_cache,
            server_names=set(config.servers.keys()),
        )
        chat._config = config

        assert chat._config is config
        assert chat._tool_discovery_config is None
        assert not chat._is_discovery_enabled()

    async def test_discovery_disabled_when_config_none_but_discovery_config_set(
        self,
    ) -> None:
        """_is_discovery_enabled should be False when config is None even with discovery_config."""
        mock_client = AsyncMock()
        mock_model = AsyncMock(spec=Model)
        mock_model.get_usage = Mock(return_value=None)
        mock_tool_cache = Mock()
        mock_tool_cache.get_tools = AsyncMock(return_value=[])
        mock_tool_cache.version = 1

        # Set tool_discovery_config without config
        chat = McpToolChat(
            mock_client,
            "System prompt",
            tool_cache=mock_tool_cache,
        )
        chat._tool_discovery_config = ToolDiscoveryConfig(enabled=True)

        # Even though tool_discovery_config.enabled is True,
        # _is_discovery_enabled() requires config to be non-None
        assert chat._tool_discovery_config is not None
        assert chat._tool_discovery_config.enabled is True
        assert chat._config is None
        assert not chat._is_discovery_enabled()


# ---------------------------------------------------------------------------
# Stats: discovery metrics tracked during chat
# ---------------------------------------------------------------------------


class TestDiscoveryStatsInChat:
    """Tests that discovery stats are tracked in the chat loop."""

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

    async def test_discovery_stats_present_when_enabled(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Stats should include discovery when enabled."""
        weather_tool = _make_tool("weather_get", "Get weather")
        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.discovery is not None
        assert stats.discovery.search_calls == 0
        assert stats.discovery.tools_discovered == 0

    async def test_discovery_stats_none_when_disabled(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Stats should not include discovery when disabled."""
        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"math": {"defer_loading": False}},
            discovery=ToolDiscoveryConfig(enabled=False),
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"math"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.discovery is None

    async def test_discovery_stats_none_when_no_config(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Stats should not include discovery without any config."""
        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[])
        type(tool_cache).version = PropertyMock(return_value=1)

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        assert stats.discovery is None

    async def test_discovery_stats_track_search_calls(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Discovery stats should count search-tools invocations."""
        weather_tool = _make_tool("weather_get", "Get weather forecast")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Search for weather tool
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
        assert stats.discovery is not None
        assert stats.discovery.search_calls == 1
        assert stats.discovery.tools_discovered == 1  # weather_get found

    async def test_discovery_stats_track_tools_discovered(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Discovery stats should count newly discovered tools."""
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

        # First search loads forecast
        search_call_1 = AssistantToolCall(
            id="call_s1",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "forecast"}',
            ),
        )
        # Second search loads current
        search_call_2 = AssistantToolCall(
            id="call_s2",
            function=AssistantToolCallFunction(
                name="search-tools",
                arguments='{"query": "current"}',
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

        stats = chat.get_stats()
        assert stats is not None
        assert stats.discovery is not None
        assert stats.discovery.search_calls == 2
        # Both tools should have been discovered across the two searches
        assert stats.discovery.tools_discovered >= 2

    async def test_discovery_stats_no_results_search(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Discovery stats should track search call even with no results."""
        weather_tool = _make_tool("weather_get", "Get weather forecast")

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        # Search for something that won't match
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
        assert stats.discovery is not None
        assert stats.discovery.search_calls == 1
        assert stats.discovery.tools_discovered == 0

    async def test_discovery_stats_in_serialized_output(
        self, mock_client: AsyncMock, mock_model: AsyncMock
    ) -> None:
        """Discovery stats should be present in serialized stats output."""
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
                arguments='{"tool_names": ["weather_get"]}',
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
        data = stats.model_dump()
        assert data["discovery"] is not None
        assert data["discovery"]["search_calls"] == 1
        assert data["discovery"]["tools_discovered"] == 1


# ---------------------------------------------------------------------------
# CLI: tools command shows deferred status
# ---------------------------------------------------------------------------


class TestCLIToolsCommand:
    """Tests for the CLI tools command with tool discovery."""

    def test_tools_table_with_discovery_enabled(self) -> None:
        """CLI tools command should show Status column when discovery is enabled."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        tool_list = [
            _make_tool("math_add", "Add two numbers"),
            _make_tool("weather_get", "Get weather"),
        ]

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=tool_list),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            # Verify table was printed
            mock_console.print.assert_called_once()
            table = mock_console.print.call_args[0][0]
            # Table should have 3 columns (Name, Description, Status)
            assert len(table.columns) == 3
            assert table.columns[2].header == "Status"

    def test_tools_table_correct_status_labels(self) -> None:
        """CLI tools command should mark deferred tools and loaded tools correctly."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={
                "math": {"defer_loading": False},
                "weather": {"defer_loading": True},
            },
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        tool_list = [
            _make_tool("math_add", "Add two numbers"),
            _make_tool("weather_get", "Get weather"),
        ]

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=tool_list),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            table = mock_console.print.call_args[0][0]
            # Build name->status mapping from the table
            names = list(table.columns[0].cells)
            statuses = list(table.columns[2].cells)
            status_map = dict(zip(names, statuses))

            # math_add should be loaded (math server defer_loading=False)
            assert status_map["math_add"] == "loaded"
            # weather_get should be deferred (weather server defer_loading=True)
            assert "[yellow]deferred[/yellow]" in status_map["weather_get"]

    def test_tools_table_all_tools_deferred(self) -> None:
        """CLI tools command shows all tools as deferred when all servers defer."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        tool_list = [
            _make_tool("weather_get", "Get weather"),
            _make_tool("weather_forecast", "Get forecast"),
        ]

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=tool_list),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            table = mock_console.print.call_args[0][0]
            statuses = list(table.columns[2].cells)
            # All tools should be deferred
            for status in statuses:
                assert "deferred" in status

    def test_tools_table_empty_tool_list_with_discovery(self) -> None:
        """CLI tools command handles empty tool list with discovery enabled."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=[]),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            table = mock_console.print.call_args[0][0]
            # Table should have 3 columns (Status is present) but no rows
            assert len(table.columns) == 3
            assert len(list(table.columns[0].cells)) == 0

    def test_tools_table_without_discovery(self) -> None:
        """CLI tools command should not show Status column without discovery."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={"math": {"defer_loading": False}},
        )

        tool_list = [_make_tool("math_add", "Add two numbers")]

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=tool_list),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            mock_console.print.assert_called_once()
            table = mock_console.print.call_args[0][0]
            # Table should have 2 columns (Name, Description)
            assert len(table.columns) == 2

    def test_tools_table_with_discovery_disabled(self) -> None:
        """CLI tools command without Status column when discovery present but disabled."""
        from casual_mcp.cli import tools as tools_command

        config = _make_config(
            servers={"math": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=False),
        )

        tool_list = [_make_tool("math_add", "Add two numbers")]

        with (
            patch("casual_mcp.cli.load_config", return_value=config),
            patch("casual_mcp.cli.load_mcp_client", return_value=Mock()),
            patch("casual_mcp.cli.run_async_with_cleanup", return_value=tool_list),
            patch("casual_mcp.cli.console") as mock_console,
        ):
            tools_command()

            mock_console.print.assert_called_once()
            table = mock_console.print.call_args[0][0]
            # Table should have 2 columns (discovery disabled)
            assert len(table.columns) == 2


# ---------------------------------------------------------------------------
# API endpoint: stats include discovery when applicable
# ---------------------------------------------------------------------------


class TestAPIStatsWithDiscovery:
    """Tests that the API returns discovery stats when applicable."""

    async def test_stats_response_includes_discovery(self) -> None:
        """When include_stats=True, response should include discovery stats."""
        weather_tool = _make_tool("weather_get", "Get weather")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_model = AsyncMock(spec=Model)
        mock_model.get_usage = Mock(return_value=None)

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[weather_tool])
        type(tool_cache).version = PropertyMock(return_value=1)

        config = _make_config(
            servers={"weather": {"defer_loading": True}},
            discovery=ToolDiscoveryConfig(enabled=True),
        )

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
            server_names={"weather"},
        )
        chat._config = config
        chat._tool_discovery_config = config.tool_discovery
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None

        # Simulate API response construction
        stats_data = stats.model_dump()
        assert "discovery" in stats_data
        assert stats_data["discovery"] is not None
        assert stats_data["discovery"]["search_calls"] == 0
        assert stats_data["discovery"]["tools_discovered"] == 0

    async def test_stats_response_no_discovery_without_config(self) -> None:
        """When discovery is not configured, stats should not include it."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_model = AsyncMock(spec=Model)
        mock_model.get_usage = Mock(return_value=None)

        tool_cache = Mock()
        tool_cache.get_tools = AsyncMock(return_value=[])
        type(tool_cache).version = PropertyMock(return_value=1)

        mock_model.chat = AsyncMock(return_value=AssistantMessage(content="Hello"))

        chat = McpToolChat(
            mock_client,
            "System",
            tool_cache,
        )
        await chat.chat([UserMessage(content="Hi")], model=mock_model)

        stats = chat.get_stats()
        assert stats is not None
        stats_data = stats.model_dump()
        assert stats_data["discovery"] is None
