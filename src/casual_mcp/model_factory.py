from casual_llm import (
    ClientConfig,
    LLMClient,
    Model,
    ModelConfig,
    create_client,
    create_model,
)

from casual_mcp.logging import get_logger
from casual_mcp.models.config import Config

logger = get_logger("model.factory")


class ModelFactory:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._clients: dict[str, LLMClient] = {}
        self._models: dict[str, Model] = {}

    def _get_or_create_client(self, client_name: str) -> LLMClient:
        existing = self._clients.get(client_name)
        if existing:
            logger.debug("Reusing cached client '%s'", client_name)
            return existing

        client_config = self._config.clients.get(client_name)
        if client_config is None:
            raise ValueError(
                f"Client '{client_name}' is not defined in clients config. "
                f"Available: {list(self._config.clients.keys())}"
            )

        logger.info("Creating client '%s' (provider=%s)", client_name, client_config.provider)
        client = create_client(
            ClientConfig(
                provider=client_config.provider,
                name=client_name,
                base_url=client_config.base_url,
                api_key=client_config.api_key.get_secret_value() if client_config.api_key else None,
                timeout=client_config.timeout,
            )
        )
        self._clients[client_name] = client
        return client

    def get_model(self, name: str) -> Model:
        existing = self._models.get(name)
        if existing:
            logger.debug("Reusing cached model '%s'", name)
            return existing

        model_config = self._config.models.get(name)
        if model_config is None:
            raise ValueError(
                f"Model '{name}' is not defined in models config. "
                f"Available: {list(self._config.models.keys())}"
            )

        client = self._get_or_create_client(model_config.client)

        logger.info(
            "Creating model '%s' (client=%s, model=%s)",
            name,
            model_config.client,
            model_config.model,
        )
        model = create_model(
            client,
            ModelConfig(
                name=model_config.model,
                temperature=model_config.temperature,
            ),
        )

        self._models[name] = model
        return model
