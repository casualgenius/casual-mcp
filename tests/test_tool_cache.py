"""Tests for ToolCache with TTL, versioning, and cache management."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from casual_mcp.tool_cache import ToolCache


class TestToolCache:
    """Tests for ToolCache functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MCP client."""
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_tools(self):
        """Create mock MCP tools."""

        class MockTool:
            def __init__(self, name):
                self.name = name
                self.description = f"Description for {name}"

        return [MockTool("tool1"), MockTool("tool2")]

    async def test_get_tools_fetches_on_first_call(self, mock_client, mock_tools):
        """Test that get_tools fetches from client on first call."""
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        cache = ToolCache(mock_client, ttl_seconds=30)

        tools = await cache.get_tools()

        assert len(tools) == 2
        assert tools[0].name == "tool1"
        mock_client.list_tools.assert_called_once()

    async def test_get_tools_uses_cache_when_fresh(self, mock_client, mock_tools):
        """Test that get_tools returns cached results when fresh."""
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        cache = ToolCache(mock_client, ttl_seconds=30)

        # First call
        await cache.get_tools()
        # Second call should use cache
        tools = await cache.get_tools()

        assert len(tools) == 2
        # Should only call list_tools once
        assert mock_client.list_tools.call_count == 1

    async def test_get_tools_refreshes_after_ttl_expires(self, mock_client, mock_tools):
        """Test that get_tools refreshes after TTL expires."""
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        cache = ToolCache(mock_client, ttl_seconds=0.1)  # 100ms TTL

        # First call
        await cache.get_tools()

        # Wait for TTL to expire
        await asyncio.sleep(0.15)

        # Second call should refresh
        await cache.get_tools()

        # Should call list_tools twice
        assert mock_client.list_tools.call_count == 2

    async def test_get_tools_with_force_refresh(self, mock_client, mock_tools):
        """Test force refresh ignores cache."""
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        cache = ToolCache(mock_client, ttl_seconds=30)

        # First call
        await cache.get_tools()
        # Force refresh
        await cache.get_tools(force_refresh=True)

        # Should call list_tools twice
        assert mock_client.list_tools.call_count == 2

    async def test_get_tools_with_infinite_ttl(self, mock_client, mock_tools):
        """Test that TTL=None means cache never expires."""
        mock_client.list_tools = AsyncMock(return_value=mock_tools)
        cache = ToolCache(mock_client, ttl_seconds=None)

        # First call
        await cache.get_tools()

        # Wait a bit
        await asyncio.sleep(0.1)

        # Second call should still use cache
        await cache.get_tools()

        # Should only call list_tools once
        assert mock_client.list_tools.call_count == 1

    def test_invalidate_clears_cache(self, mock_client):
        """Test that invalidate clears the cache."""
        cache = ToolCache(mock_client, ttl_seconds=30)
        cache.prime([Mock(name="tool1")])

        assert cache._state is not None
        cache.invalidate()
        assert cache._state is None

    def test_prime_sets_cache(self, mock_client, mock_tools):
        """Test that prime sets the cache without network call."""
        cache = ToolCache(mock_client, ttl_seconds=30)

        cache.prime(mock_tools)

        assert cache._state is not None
        assert len(cache._state.tools) == 2
        assert cache.version == 1

    def test_version_increments_on_refresh(self, mock_client, mock_tools):
        """Test that version increments when cache refreshes."""
        cache = ToolCache(mock_client, ttl_seconds=30)

        assert cache.version == 0
        cache.prime(mock_tools)
        assert cache.version == 1
        cache.prime(mock_tools)
        assert cache.version == 2

    @patch.dict("os.environ", {"MCP_TOOL_CACHE_TTL": "60"})
    def test_ttl_from_env_var(self, mock_client):
        """Test that TTL can be set from environment variable."""
        cache = ToolCache(mock_client)
        assert cache._ttl == 60.0

    @patch.dict("os.environ", {"MCP_TOOL_CACHE_TTL": "0"})
    def test_ttl_zero_means_infinite(self, mock_client):
        """Test that TTL=0 means infinite cache."""
        cache = ToolCache(mock_client)
        assert cache._ttl is None

    @patch.dict("os.environ", {"MCP_TOOL_CACHE_TTL": "invalid"})
    def test_invalid_ttl_uses_default(self, mock_client):
        """Test that invalid TTL falls back to default."""
        cache = ToolCache(mock_client)
        assert cache._ttl == 30.0  # Default

    async def test_concurrent_access_uses_lock(self, mock_client, mock_tools):
        """Test that concurrent get_tools calls use lock correctly."""
        call_count = 0

        # Slow list_tools to test locking
        async def slow_list_tools():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return mock_tools

        mock_client.list_tools = slow_list_tools
        cache = ToolCache(mock_client, ttl_seconds=30)

        # Start two concurrent requests
        results = await asyncio.gather(cache.get_tools(), cache.get_tools())

        # Both should get the same tools
        assert len(results[0]) == 2
        assert len(results[1]) == 2
        # But list_tools should only be called once due to lock
        assert call_count == 1
