"""Shared pytest fixtures."""

import pytest


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
