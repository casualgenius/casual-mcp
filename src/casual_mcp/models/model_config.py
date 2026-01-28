from typing import Literal

from pydantic import BaseModel


class BaseModelConfig(BaseModel):
    provider: Literal["openai", "ollama"]
    model: str
    endpoint: str | None = None
    template: str | None = None


class OpenAIModelConfig(BaseModelConfig):
    provider: Literal["openai"]


class OllamaModelConfig(BaseModelConfig):
    provider: Literal["ollama"]


McpModelConfig = OpenAIModelConfig | OllamaModelConfig
