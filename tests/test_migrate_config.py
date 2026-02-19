"""Tests for migrate_legacy_config CLI function."""

from casual_mcp.cli import migrate_legacy_config


class TestMigrateLegacyConfig:
    """Tests for the migrate_legacy_config function."""

    def test_migrates_basic_legacy_config(self):
        """Test migration of a basic legacy config."""
        data = {
            "models": {
                "test-model": {"provider": "openai", "model": "gpt-4"},
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        assert "openai" in result["clients"]
        assert result["clients"]["openai"]["provider"] == "openai"
        assert result["models"]["test-model"]["client"] == "openai"
        assert result["models"]["test-model"]["model"] == "gpt-4"

    def test_migrates_with_endpoint(self):
        """Test migration preserves endpoint as base_url."""
        data = {
            "models": {
                "ollama-model": {
                    "provider": "ollama",
                    "model": "llama2",
                    "endpoint": "http://localhost:11434",
                },
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        assert "ollama" in result["clients"]
        assert result["clients"]["ollama"]["base_url"] == "http://localhost:11434"
        assert result["models"]["ollama-model"]["client"] == "ollama"

    def test_migrates_preserves_template(self):
        """Test migration preserves template field."""
        data = {
            "models": {
                "test": {"provider": "openai", "model": "gpt-4", "template": "my-template"},
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        assert result["models"]["test"]["template"] == "my-template"

    def test_migrates_preserves_temperature(self):
        """Test migration preserves temperature field."""
        data = {
            "models": {
                "test": {"provider": "openai", "model": "gpt-4", "temperature": 0.7},
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        assert result["models"]["test"]["temperature"] == 0.7

    def test_returns_none_for_new_format(self):
        """Test that new-format config returns None (no migration needed)."""
        data = {
            "clients": {"openai": {"provider": "openai"}},
            "models": {"test": {"client": "openai", "model": "gpt-4"}},
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is None

    def test_returns_none_for_empty_models(self):
        """Test that config with no models returns None."""
        data = {"models": {}, "servers": {}}

        result = migrate_legacy_config(data)

        assert result is None

    def test_deduplicates_same_provider_different_endpoints(self):
        """Test that multiple endpoints for same provider get unique client names."""
        data = {
            "models": {
                "model1": {
                    "provider": "ollama",
                    "model": "llama2",
                    "endpoint": "http://host1:11434",
                },
                "model2": {
                    "provider": "ollama",
                    "model": "llama3",
                    "endpoint": "http://host2:11434",
                },
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        clients = result["clients"]
        assert len(clients) == 2
        # One should be "ollama", the other "ollama-2"
        assert "ollama" in clients
        assert "ollama-2" in clients

    def test_multiple_models_share_same_client(self):
        """Test that models with same provider/endpoint share a client."""
        data = {
            "models": {
                "model1": {"provider": "openai", "model": "gpt-4"},
                "model2": {"provider": "openai", "model": "gpt-4-mini"},
            },
            "servers": {},
        }

        result = migrate_legacy_config(data)

        assert result is not None
        assert len(result["clients"]) == 1
        assert result["models"]["model1"]["client"] == "openai"
        assert result["models"]["model2"]["client"] == "openai"
