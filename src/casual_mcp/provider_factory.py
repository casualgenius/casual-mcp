import os

from casual_llm import (
    LLMProvider,
    ModelConfig,
    Provider,
    create_provider,
)

from casual_mcp.logging import get_logger
from casual_mcp.models.model_config import McpModelConfig

logger = get_logger("providers.factory")


class ProviderFactory:
    def __init__(self) -> None:
        self.providers: dict[str, LLMProvider] = {}

    def get_provider(self, name: str, config: McpModelConfig) -> LLMProvider:
        existing = self.providers.get(name)
        if existing:
            return existing

        provider_map = {
            "openai": Provider.OPENAI,
            "ollama": Provider.OLLAMA,
        }
        provider = provider_map.get(config.provider)
        if provider is None:
            raise ValueError(f"Unknown provider: {config.provider}")

        # Use casual-llm create provider
        api_key = os.getenv("OPENAI_API_KEY") if provider == Provider.OPENAI else None
        llm_provider = create_provider(
            ModelConfig(
                provider=provider,
                name=config.model,
                base_url=config.endpoint,
                api_key=api_key,
            )
        )

        # add to providers and return
        self.providers[name] = llm_provider
        return llm_provider
