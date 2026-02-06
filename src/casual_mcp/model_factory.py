import os

from casual_llm import (
    ClientConfig,
    LLMClient,
    Model,
    ModelConfig,
    Provider,
    create_client,
    create_model,
)

from casual_mcp.logging import get_logger
from casual_mcp.models.model_config import McpModelConfig

logger = get_logger("model.factory")


class ModelFactory:
    PROVIDER_MAP = {
        "openai": Provider.OPENAI,
        "ollama": Provider.OLLAMA,
    }

    def __init__(self) -> None:
        self._clients: dict[str, LLMClient] = {}
        self._models: dict[str, Model] = {}

    def _get_client_key(self, provider: Provider, endpoint: str | None) -> str:
        return f"{provider.value}:{endpoint or 'default'}"

    def _get_or_create_client(
        self, provider: Provider, endpoint: str | None, api_key: str | None
    ) -> LLMClient:
        key = self._get_client_key(provider, endpoint)
        existing = self._clients.get(key)
        if existing:
            logger.debug("Reusing cached client for %s", key)
            return existing

        logger.info("Creating client for %s", key)
        client = create_client(
            ClientConfig(
                provider=provider,
                base_url=endpoint,
                api_key=api_key,
            )
        )
        self._clients[key] = client
        return client

    def get_model(self, name: str, config: McpModelConfig) -> Model:
        existing = self._models.get(name)
        if existing:
            logger.debug("Reusing cached model '%s'", name)
            return existing

        provider = self.PROVIDER_MAP.get(config.provider)
        if provider is None:
            logger.error("Unknown provider '%s' for model '%s'", config.provider, name)
            raise ValueError(f"Unknown provider: {config.provider}")

        api_key = os.getenv("OPENAI_API_KEY") if provider == Provider.OPENAI else None
        client = self._get_or_create_client(provider, config.endpoint, api_key)

        logger.info("Creating model '%s' (provider=%s, model=%s)", name, config.provider, config.model)
        model = create_model(
            client,
            ModelConfig(name=config.model),
        )

        self._models[name] = model
        return model


# Backwards compatibility alias
ProviderFactory = ModelFactory
