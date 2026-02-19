"""Tests for ModelFactory."""

from unittest.mock import Mock, patch

import pytest

from casual_llm import Provider

from casual_mcp.models.config import Config, McpClientConfig, McpModelConfig
from casual_mcp.model_factory import ModelFactory


def make_config(
    clients: dict[str, McpClientConfig],
    models: dict[str, McpModelConfig],
) -> Config:
    """Build a Config with empty servers for testing."""
    return Config(clients=clients, models=models, servers={})


class TestModelFactory:
    """Tests for ModelFactory."""

    @pytest.fixture
    def config(self):
        return make_config(
            clients={
                "openai": McpClientConfig(provider="openai", base_url="https://api.openai.com/v1"),
                "ollama": McpClientConfig(provider="ollama", base_url="http://localhost:11434"),
            },
            models={
                "test-model": McpModelConfig(client="openai", model="gpt-4"),
                "ollama-model": McpModelConfig(client="ollama", model="llama2"),
            },
        )

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_openai_model(self, mock_create_client, mock_create_model, config):
        """Test creating OpenAI model."""
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        model = factory.get_model("test-model")

        assert model == mock_create_model.return_value
        mock_create_client.assert_called_once()
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_ollama_model(self, mock_create_client, mock_create_model, config):
        """Test creating Ollama model."""
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        model = factory.get_model("ollama-model")

        assert model == mock_create_model.return_value
        mock_create_client.assert_called_once()
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_caches_model(self, mock_create_client, mock_create_model, config):
        """Test that model is cached."""
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)

        model1 = factory.get_model("test-model")
        model2 = factory.get_model("test-model")

        assert model1 is model2
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_different_models(self, mock_create_client, mock_create_model):
        """Test that different model names create different models."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai")},
            models={
                "model1": McpModelConfig(client="openai", model="gpt-4"),
                "model2": McpModelConfig(client="openai", model="gpt-4-mini"),
            },
        )
        mock_create_client.return_value = Mock()
        mock_model1 = Mock()
        mock_model2 = Mock()
        mock_create_model.side_effect = [mock_model1, mock_model2]

        factory = ModelFactory(config)

        model1 = factory.get_model("model1")
        model2 = factory.get_model("model2")

        assert model1 is not model2
        assert mock_create_model.call_count == 2

    def test_get_model_unknown_model_raises(self):
        """Test that requesting an unknown model raises ValueError."""
        config = make_config(clients={}, models={})
        factory = ModelFactory(config)

        with pytest.raises(ValueError, match="Model 'nonexistent' is not defined"):
            factory.get_model("nonexistent")

    def test_get_model_unknown_client_raises(self):
        """Test that referencing an unknown client raises ValueError."""
        config = make_config(
            clients={},
            models={"test": McpModelConfig(client="nonexistent", model="test")},
        )
        factory = ModelFactory(config)

        with pytest.raises(ValueError, match="Client 'nonexistent' is not defined"):
            factory.get_model("test")

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_passes_client_name_for_api_key_lookup(
        self, mock_create_client, mock_create_model
    ):
        """Test that client name is passed to ClientConfig for env var API key lookup."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai")},
            models={"test": McpModelConfig(client="openai", model="gpt-4")},
        )
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        factory.get_model("test")

        call_args = mock_create_client.call_args
        assert call_args[0][0].name == "openai"

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_passes_explicit_api_key(self, mock_create_client, mock_create_model):
        """Test that explicit api_key in config is passed through."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai", api_key="explicit-key")},
            models={"test": McpModelConfig(client="openai", model="gpt-4")},
        )
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        factory.get_model("test")

        call_args = mock_create_client.call_args
        assert call_args[0][0].api_key == "explicit-key"

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_shares_client_by_name(self, mock_create_client, mock_create_model):
        """Test that models referencing the same client share one client instance."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai")},
            models={
                "model1": McpModelConfig(client="openai", model="gpt-4"),
                "model2": McpModelConfig(client="openai", model="gpt-4-mini"),
            },
        )
        mock_create_client.return_value = Mock()
        mock_create_model.side_effect = [Mock(), Mock()]

        factory = ModelFactory(config)
        factory.get_model("model1")
        factory.get_model("model2")

        mock_create_client.assert_called_once()
        assert mock_create_model.call_count == 2

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_separate_clients_for_different_names(
        self, mock_create_client, mock_create_model
    ):
        """Test that different client names create separate clients."""
        config = make_config(
            clients={
                "openai": McpClientConfig(provider="openai"),
                "ollama": McpClientConfig(provider="ollama", base_url="http://localhost:11434"),
            },
            models={
                "model1": McpModelConfig(client="openai", model="gpt-4"),
                "model2": McpModelConfig(client="ollama", model="llama2"),
            },
        )
        mock_create_client.side_effect = [Mock(), Mock()]
        mock_create_model.side_effect = [Mock(), Mock()]

        factory = ModelFactory(config)
        factory.get_model("model1")
        factory.get_model("model2")

        assert mock_create_client.call_count == 2

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_passes_temperature(self, mock_create_client, mock_create_model):
        """Test that temperature is passed through to ModelConfig."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai")},
            models={"test": McpModelConfig(client="openai", model="gpt-4", temperature=0.7)},
        )
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        factory.get_model("test")

        call_args = mock_create_model.call_args
        assert call_args[0][1].temperature == 0.7

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_passes_provider_as_string(self, mock_create_client, mock_create_model):
        """Test that provider string is passed directly to ClientConfig."""
        config = make_config(
            clients={"openai": McpClientConfig(provider="openai")},
            models={"test": McpModelConfig(client="openai", model="gpt-4")},
        )
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory(config)
        factory.get_model("test")

        call_args = mock_create_client.call_args
        # casual-llm coerces string to Provider enum in ClientConfig.__post_init__
        assert call_args[0][0].provider == Provider.OPENAI
