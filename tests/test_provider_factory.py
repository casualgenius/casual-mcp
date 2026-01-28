"""Tests for ProviderFactory."""

from unittest.mock import Mock, patch

import pytest

from casual_mcp.models.model_config import OllamaModelConfig, OpenAIModelConfig
from casual_mcp.provider_factory import ProviderFactory


class TestProviderFactory:
    """Tests for ProviderFactory."""

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

    @patch("casual_mcp.provider_factory.create_provider")
    async def test_get_provider_creates_openai_provider(self, mock_create, openai_config):
        """Test creating OpenAI provider."""
        mock_provider = Mock()
        mock_create.return_value = mock_provider

        factory = ProviderFactory()
        provider = await factory.get_provider("test-model", openai_config)

        assert provider == mock_provider
        mock_create.assert_called_once()

    @patch("casual_mcp.provider_factory.create_provider")
    async def test_get_provider_creates_ollama_provider(self, mock_create, ollama_config):
        """Test creating Ollama provider."""
        mock_provider = Mock()
        mock_create.return_value = mock_provider

        factory = ProviderFactory()
        provider = await factory.get_provider("test-model", ollama_config)

        assert provider == mock_provider
        mock_create.assert_called_once()

    @patch("casual_mcp.provider_factory.create_provider")
    async def test_get_provider_caches_provider(self, mock_create, openai_config):
        """Test that provider is cached."""
        mock_provider = Mock()
        mock_create.return_value = mock_provider

        factory = ProviderFactory()

        # First call
        provider1 = await factory.get_provider("test-model", openai_config)
        # Second call with same name
        provider2 = await factory.get_provider("test-model", openai_config)

        assert provider1 is provider2
        # Should only create once
        mock_create.assert_called_once()

    @patch("casual_mcp.provider_factory.create_provider")
    async def test_get_provider_creates_different_providers(self, mock_create, openai_config):
        """Test that different model names create different providers."""
        mock_provider1 = Mock()
        mock_provider2 = Mock()
        mock_create.side_effect = [mock_provider1, mock_provider2]

        factory = ProviderFactory()

        provider1 = await factory.get_provider("model1", openai_config)
        provider2 = await factory.get_provider("model2", openai_config)

        assert provider1 is not provider2
        assert mock_create.call_count == 2

    async def test_get_provider_unknown_provider_raises(self):
        """Test that unknown provider raises ValueError."""
        # Create a mock config with invalid provider
        from unittest.mock import Mock

        config = Mock()
        config.provider = "unknown"
        config.model = "test"
        factory = ProviderFactory()

        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            await factory.get_provider("test", config)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("casual_mcp.provider_factory.create_provider")
    async def test_get_provider_uses_api_key_from_env(self, mock_create, openai_config):
        """Test that API key is read from environment."""
        factory = ProviderFactory()
        await factory.get_provider("test", openai_config)

        # Check that create_provider was called with API key
        call_args = mock_create.call_args
        assert call_args[0][0].api_key == "test-key"
