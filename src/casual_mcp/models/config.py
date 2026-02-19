import warnings
from typing import Any

from pydantic import BaseModel, Field, model_validator

from casual_mcp.models.mcp_server_config import McpServerConfig
from casual_mcp.models.toolset_config import ToolSetConfig


class McpClientConfig(BaseModel):
    """Configuration for an LLM API client connection.

    Maps to casual-llm's ClientConfig.
    """

    provider: str
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 60.0


class McpModelConfig(BaseModel):
    """Configuration for an LLM model.

    References a named client and specifies model-specific settings.
    Maps to casual-llm's ModelConfig.
    """

    client: str
    model: str
    template: str | None = None
    temperature: float | None = None


class Config(BaseModel):
    namespace_tools: bool | None = False
    clients: dict[str, McpClientConfig] = Field(default_factory=dict)
    models: dict[str, McpModelConfig]
    servers: dict[str, McpServerConfig]
    tool_sets: dict[str, ToolSetConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_config(cls, data: Any) -> Any:
        """Auto-migrate old-style configs where models contain provider/endpoint."""
        if not isinstance(data, dict):
            return data

        # If clients already exist, assume new format
        if "clients" in data and data["clients"]:
            return data

        models = data.get("models", {})
        if not models:
            return data

        # Check if any model has "provider" (old style) rather than "client" (new style)
        has_legacy = any(
            isinstance(m, dict) and "provider" in m for m in models.values()
        )
        if not has_legacy:
            return data

        warnings.warn(
            "Config uses legacy format with provider/endpoint in models. "
            "Migrate to clients/models split.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Build clients dict from unique (provider, endpoint) combos
        clients: dict[str, dict[str, Any]] = {}
        client_key_map: dict[tuple[str, str | None], str] = {}

        for model_data in models.values():
            if not isinstance(model_data, dict) or "provider" not in model_data:
                continue
            provider = model_data["provider"]
            endpoint = model_data.get("endpoint")
            key = (provider, endpoint)

            if key not in client_key_map:
                client_name = provider
                # Deduplicate if multiple endpoints for same provider
                suffix = 1
                while client_name in clients:
                    suffix += 1
                    client_name = f"{provider}-{suffix}"

                client_config: dict[str, Any] = {"provider": provider}
                if endpoint:
                    client_config["base_url"] = endpoint
                clients[client_name] = client_config
                client_key_map[key] = client_name

        # Rewrite models to reference clients
        new_models: dict[str, dict[str, Any]] = {}
        for model_name, model_data in models.items():
            if not isinstance(model_data, dict):
                new_models[model_name] = model_data
                continue
            provider = model_data.get("provider")
            endpoint = model_data.get("endpoint")
            key = (provider, endpoint)
            client_name = client_key_map.get(key, provider)

            new_model: dict[str, Any] = {
                "client": client_name,
                "model": model_data["model"],
            }
            if "template" in model_data:
                new_model["template"] = model_data["template"]
            new_models[model_name] = new_model

        data["clients"] = clients
        data["models"] = new_models
        return data
