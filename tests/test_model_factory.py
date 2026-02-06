"""Tests for ModelFactory."""

from unittest.mock import Mock, patch

import pytest

from casual_mcp.models.model_config import OllamaModelConfig, OpenAIModelConfig
from casual_mcp.model_factory import ModelFactory


class TestModelFactory:
    """Tests for ModelFactory."""

    @pytest.fixture
    def openai_config(self):
        """Create OpenAI model config."""
        return OpenAIModelConfig(
            provider="openai", model="gpt-4", endpoint="https://api.openai.com/v1"
        )

    @pytest.fixture
    def ollama_config(self):
        """Create Ollama model config."""
        return OllamaModelConfig(
            provider="ollama", model="llama2", endpoint="http://localhost:11434"
        )

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_openai_model(
        self, mock_create_client, mock_create_model, openai_config
    ):
        """Test creating OpenAI model."""
        mock_client = Mock()
        mock_model = Mock()
        mock_create_client.return_value = mock_client
        mock_create_model.return_value = mock_model

        factory = ModelFactory()
        model = factory.get_model("test-model", openai_config)

        assert model == mock_model
        mock_create_client.assert_called_once()
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_ollama_model(
        self, mock_create_client, mock_create_model, ollama_config
    ):
        """Test creating Ollama model."""
        mock_client = Mock()
        mock_model = Mock()
        mock_create_client.return_value = mock_client
        mock_create_model.return_value = mock_model

        factory = ModelFactory()
        model = factory.get_model("test-model", ollama_config)

        assert model == mock_model
        mock_create_client.assert_called_once()
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_caches_model(self, mock_create_client, mock_create_model, openai_config):
        """Test that model is cached."""
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory()

        # First call
        model1 = factory.get_model("test-model", openai_config)
        # Second call with same name
        model2 = factory.get_model("test-model", openai_config)

        assert model1 is model2
        # Should only create once
        mock_create_model.assert_called_once()

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_different_models(
        self, mock_create_client, mock_create_model, openai_config
    ):
        """Test that different model names create different models."""
        mock_create_client.return_value = Mock()
        mock_model1 = Mock()
        mock_model2 = Mock()
        mock_create_model.side_effect = [mock_model1, mock_model2]

        factory = ModelFactory()

        model1 = factory.get_model("model1", openai_config)
        model2 = factory.get_model("model2", openai_config)

        assert model1 is not model2
        assert mock_create_model.call_count == 2

    def test_get_model_unknown_provider_raises(self):
        """Test that unknown provider raises ValueError."""
        config = Mock()
        config.provider = "unknown"
        config.model = "test"
        factory = ModelFactory()

        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            factory.get_model("test", config)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_uses_api_key_from_env(
        self, mock_create_client, mock_create_model, openai_config
    ):
        """Test that API key is read from environment for OpenAI."""
        mock_create_client.return_value = Mock()
        mock_create_model.return_value = Mock()

        factory = ModelFactory()
        factory.get_model("test", openai_config)

        # Check that create_client was called with API key
        call_args = mock_create_client.call_args
        assert call_args[0][0].api_key == "test-key"

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_shares_client_for_same_endpoint(self, mock_create_client, mock_create_model):
        """Test that models with the same provider+endpoint share a client."""
        config1 = OpenAIModelConfig(
            provider="openai", model="gpt-4", endpoint="https://api.openai.com/v1"
        )
        config2 = OpenAIModelConfig(
            provider="openai", model="gpt-4-mini", endpoint="https://api.openai.com/v1"
        )

        mock_create_client.return_value = Mock()
        mock_create_model.side_effect = [Mock(), Mock()]

        factory = ModelFactory()
        factory.get_model("model1", config1)
        factory.get_model("model2", config2)

        # Client should only be created once (same provider + endpoint)
        mock_create_client.assert_called_once()
        # But two models should be created
        assert mock_create_model.call_count == 2

    @patch("casual_mcp.model_factory.create_model")
    @patch("casual_mcp.model_factory.create_client")
    def test_get_model_creates_separate_clients_for_different_endpoints(
        self, mock_create_client, mock_create_model
    ):
        """Test that different endpoints create separate clients."""
        config1 = OpenAIModelConfig(
            provider="openai", model="gpt-4", endpoint="https://api.openai.com/v1"
        )
        config2 = OllamaModelConfig(
            provider="ollama", model="llama2", endpoint="http://localhost:11434"
        )

        mock_create_client.side_effect = [Mock(), Mock()]
        mock_create_model.side_effect = [Mock(), Mock()]

        factory = ModelFactory()
        factory.get_model("model1", config1)
        factory.get_model("model2", config2)

        # Should create two separate clients (different providers)
        assert mock_create_client.call_count == 2
