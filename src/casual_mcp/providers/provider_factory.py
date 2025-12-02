import os

import mcp
from casual_llm import (
    AssistantMessage,
    ChatMessage,
    LLMProvider,
    ModelConfig,
    Provider,
    create_provider,
)
from fastmcp import Client

from casual_mcp.convert_tools import tools_from_mcp
from casual_mcp.logging import get_logger
from casual_mcp.models.model_config import McpModelConfig
from casual_mcp.tool_cache import ToolCache

logger = get_logger("providers.factory")

class CasualMcpProvider:
    def __init__(self, provider: LLMProvider, tools: list[mcp.Tool]):
        self.provider = provider
        self.tools = tools_from_mcp(tools)

    async def generate(
        self,
        messages: list[ChatMessage],
        tools: list[mcp.Tool]
    ) -> AssistantMessage:
        # print(self.tools)
        return await self.provider.chat(messages=messages, tools=self.tools)

    def update_tools(self, tools: list[mcp.Tool]) -> None:
        """
        Allow providers to refresh their tool catalogue when it changes.
        Default implementation is a no-op for providers that do not need it.
        """
        self.tools = tools_from_mcp(tools)


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


    async def get_provider(self, name: str, config: McpModelConfig) -> CasualMcpProvider:
        tools = await self.tool_cache.get_tools()
        if self.tool_cache.version != self._tool_cache_version:
            logger.info("Tool cache refreshed; updating providers")
            self.tools = tools
            self._tool_cache_version = self.tool_cache.version
            for provider in self.providers.values():
                provider.update_tools(tools)

        if self.providers.get(name):
            return self.providers.get(name)


        if (config.provider == "openai"):
            provider = Provider.OPENAI
        elif (config.provider == "ollama"):
            provider = Provider.OLLAMA
        else:
            raise ValueError(f"Unknown provider: {config.provider}")


        # Use casual-llm create provider
        llm_provider = create_provider(
            ModelConfig(
                provider=provider,
                name=config.model,
                base_url=config.endpoint,
                api_key=os.getenv("OPEN_AI_API_KEY")
            )
        )

        # create the casual mcp provider
        provider = CasualMcpProvider(llm_provider, tools)

        # add to providers and return
        self.providers[name] = provider
        return provider
