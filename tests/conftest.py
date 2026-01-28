"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def sample_config_data():
    """Sample configuration data for tests."""
    return {
        "models": {
            "gpt-4": {
                "provider": "openai",
                "model": "gpt-4",
                "endpoint": "https://api.openai.com/v1",
            },
            "llama2": {
                "provider": "ollama",
                "model": "llama2",
                "endpoint": "http://localhost:11434",
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
