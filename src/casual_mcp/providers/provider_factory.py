import os
from typing import TypeAlias

import mcp
from fastmcp import Client

from casual_mcp.logging import get_logger
from casual_mcp.models.model_config import ModelConfig
from casual_mcp.providers.ollama_provider import OllamaProvider
from casual_mcp.providers.openai_provider import OpenAiProvider
from casual_mcp.tool_cache import ToolCache

logger = get_logger("providers.factory")

LLMProvider: TypeAlias = OpenAiProvider | OllamaProvider

class ProviderFactory:
    def __init__(self, mcp_client: Client, tool_cache: ToolCache | None = None):
        self.mcp_client = mcp_client
        self.tool_cache = tool_cache or ToolCache(mcp_client)
        self.providers: dict[str, LLMProvider] = {}
        self.tools: list[mcp.Tool] | None = None
        self._tool_cache_version: int = -1


    def set_tools(self, tools: list[mcp.Tool]):
        self.tools = tools
        self.tool_cache.prime(tools)
        self._tool_cache_version = self.tool_cache.version


    async def get_provider(self, name: str, config: ModelConfig) -> LLMProvider:
        tools = await self.tool_cache.get_tools()
        if self.tool_cache.version != self._tool_cache_version:
            logger.info("Tool cache refreshed; updating providers")
            self.tools = tools
            self._tool_cache_version = self.tool_cache.version
            for provider in self.providers.values():
                provider.update_tools(tools)

        if self.providers.get(name):
            return self.providers.get(name)

        match config.provider:
            case "ollama":
                logger.info(f"Creating Ollama provider for {config.model} at {config.endpoint}")
                provider = OllamaProvider(config.model, endpoint=config.endpoint.__str__())

            case "openai":
                endpoint = None
                if config.endpoint:
                    endpoint = config.endpoint.__str__()

                logger.info(f"Creating OpenAI provider for {config.model} at {endpoint}")
                api_key = os.getenv("OPEN_AI_API_KEY")
                provider = OpenAiProvider(
                    config.model,
                    api_key,
                    tools,
                    endpoint=endpoint,
                )

        self.providers[name] = provider
        return provider
