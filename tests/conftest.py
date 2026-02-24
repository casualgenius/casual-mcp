"""Shared pytest fixtures."""

import pytest
from unittest.mock import AsyncMock, Mock

from casual_llm import Model


@pytest.fixture
def mock_client():
    """Create a mock MCP client with async context manager support."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_model():
    """Create a mock LLM model."""
    model = AsyncMock(spec=Model)
    model.get_usage = Mock(return_value=None)
    return model


@pytest.fixture
def mock_tool_cache():
    """Create a mock tool cache with empty tool list."""
    cache = Mock()
    cache.get_tools = AsyncMock(return_value=[])
    cache.version = 1
    return cache


@pytest.fixture
def sample_config_data():
    """Sample configuration data for tests."""
    return {
        "clients": {
            "openai": {
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
            },
            "ollama": {
                "provider": "ollama",
                "base_url": "http://localhost:11434",
            },
        },
        "models": {
            "gpt-4": {
                "client": "openai",
                "model": "gpt-4",
            },
            "llama2": {
                "client": "ollama",
                "model": "llama2",
            },
        },
        "servers": {"test-server": {"command": "python", "args": ["-m", "test_server"], "env": {}}},
    }


@pytest.fixture
def temp_template_dir(tmp_path):
    """Create a temporary template directory."""
    template_dir = tmp_path / "prompt-templates"
    template_dir.mkdir()
    return template_dir
