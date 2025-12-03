import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import mcp
from fastmcp import Client

from casual_mcp.logging import get_logger

logger = get_logger("tool_cache")


def _parse_ttl(value: str | None) -> float | None:
    """
    Convert an environment value to a TTL in seconds.

    Returns None for non-positive values to indicate no expiry.
    """
    if value is None:
        return 30.0

    try:
        ttl = float(value)
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid MCP_TOOL_CACHE_TTL value '{value}'. Falling back to default of 30s."
        )
        return 30.0

    if ttl <= 0:
        return None

    return ttl


@dataclass(slots=True)
class _ToolCacheState:
    tools: list[mcp.Tool]
    fetched_at: float


class ToolCache:
    """
    Cache for list_tools responses to avoid hitting MCP servers on every request.

    The cache honours a TTL (default 30 seconds) that can be overridden with the
    MCP_TOOL_CACHE_TTL environment variable. Setting the TTL to a non-positive
    number disables expiry (cache forever unless manually invalidated).
    """

    def __init__(self, client: Client[Any], ttl_seconds: float | None = None):
        self._client = client
        self._ttl = (
            ttl_seconds if ttl_seconds is not None else _parse_ttl(os.getenv("MCP_TOOL_CACHE_TTL"))
        )
        self._state: _ToolCacheState | None = None
        self._lock = asyncio.Lock()
        self._version = 0

    def _is_expired(self) -> bool:
        if self._state is None:
            return True

        if self._ttl is None:
            return False

        return (time.monotonic() - self._state.fetched_at) > self._ttl

    async def get_tools(self, force_refresh: bool = False) -> list[mcp.Tool]:
        """
        Return the cached tool list, refreshing if expired or forced.
        """
        if not force_refresh and not self._is_expired() and self._state is not None:
            return self._state.tools

        async with self._lock:
            if not force_refresh and not self._is_expired() and self._state is not None:
                return self._state.tools

            logger.debug("Refreshing MCP tool cache")
            async with self._client:
                tools = await self._client.list_tools()

            self._state = _ToolCacheState(
                tools=tools,
                fetched_at=time.monotonic(),
            )
            self._version += 1

            return tools

    def invalidate(self) -> None:
        """
        Manually clear the cached tools. The next get_tools call will refetch.
        """
        self._state = None

    def prime(self, tools: list[mcp.Tool]) -> None:
        """
        Seed the cache with a known tool list without making a network call.
        """
        self._state = _ToolCacheState(
            tools=tools,
            fetched_at=time.monotonic(),
        )
        self._version += 1

    @property
    def version(self) -> int:
        return self._version
