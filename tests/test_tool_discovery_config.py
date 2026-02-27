"""Tests for tool discovery configuration models."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from casual_mcp.models import ToolDiscoveryConfig
from casual_mcp.models.config import Config
from casual_mcp.models.mcp_server_config import RemoteServerConfig, StdioServerConfig


class TestToolDiscoveryConfig:
    """Tests for the ToolDiscoveryConfig model."""

    def test_defaults(self) -> None:
        """Test that ToolDiscoveryConfig has correct default values."""
        config = ToolDiscoveryConfig()
        assert config.enabled is False
        assert config.defer_all is False
        assert config.max_search_results == 5

    def test_all_fields_set(self) -> None:
        """Test creating ToolDiscoveryConfig with all fields explicitly set."""
        config = ToolDiscoveryConfig(
            enabled=True,
            defer_all=True,
            max_search_results=10,
        )
        assert config.enabled is True
        assert config.defer_all is True
        assert config.max_search_results == 10

    def test_partial_fields(self) -> None:
        """Test creating ToolDiscoveryConfig with some fields set."""
        config = ToolDiscoveryConfig(enabled=True)
        assert config.enabled is True
        assert config.defer_all is False
        assert config.max_search_results == 5

    def test_max_search_results_minimum(self) -> None:
        """Test that max_search_results must be at least 1."""
        with pytest.raises(ValidationError):
            ToolDiscoveryConfig(max_search_results=0)

    def test_max_search_results_negative(self) -> None:
        """Test that max_search_results rejects negative values."""
        with pytest.raises(ValidationError):
            ToolDiscoveryConfig(max_search_results=-1)

    def test_from_dict(self) -> None:
        """Test creating ToolDiscoveryConfig from a dictionary."""
        data = {"enabled": True, "defer_all": False, "max_search_results": 3}
        config = ToolDiscoveryConfig.model_validate(data)
        assert config.enabled is True
        assert config.defer_all is False
        assert config.max_search_results == 3

    def test_serialization_roundtrip(self) -> None:
        """Test that serialization and deserialization produce the same result."""
        original = ToolDiscoveryConfig(enabled=True, defer_all=True, max_search_results=8)
        data = original.model_dump()
        restored = ToolDiscoveryConfig.model_validate(data)
        assert original == restored

    def test_json_roundtrip(self) -> None:
        """Test JSON serialization roundtrip."""
        original = ToolDiscoveryConfig(enabled=True, max_search_results=7)
        json_str = original.model_dump_json()
        restored = ToolDiscoveryConfig.model_validate_json(json_str)
        assert original == restored

    def test_max_search_results_boundary_at_one(self) -> None:
        """Test that max_search_results accepts exactly 1 (minimum valid)."""
        config = ToolDiscoveryConfig(max_search_results=1)
        assert config.max_search_results == 1

    def test_max_search_results_rejects_non_integer(self) -> None:
        """Test that max_search_results rejects non-numeric strings."""
        with pytest.raises(ValidationError):
            ToolDiscoveryConfig(max_search_results="abc")  # type: ignore[arg-type]

    def test_empty_dict_uses_all_defaults(self) -> None:
        """Test that an empty dict produces a config with all defaults."""
        config = ToolDiscoveryConfig.model_validate({})
        assert config.enabled is False
        assert config.defer_all is False
        assert config.max_search_results == 5


class TestStdioServerConfigDeferLoading:
    """Tests for defer_loading on StdioServerConfig."""

    def test_default_defer_loading(self) -> None:
        """Test that defer_loading defaults to False."""
        config = StdioServerConfig(command="python")
        assert config.defer_loading is False

    def test_defer_loading_true(self) -> None:
        """Test setting defer_loading to True."""
        config = StdioServerConfig(command="python", defer_loading=True)
        assert config.defer_loading is True

    def test_existing_fields_preserved(self) -> None:
        """Test that existing fields still work with defer_loading."""
        config = StdioServerConfig(
            command="python",
            args=["server.py", "--port", "8080"],
            env={"API_KEY": "secret"},
            cwd="/app",
            defer_loading=True,
        )
        assert config.command == "python"
        assert config.args == ["server.py", "--port", "8080"]
        assert config.env == {"API_KEY": "secret"}
        assert config.cwd == "/app"
        assert config.transport == "stdio"
        assert config.defer_loading is True

    def test_backward_compatible_without_defer_loading(self) -> None:
        """Test that configs without defer_loading still parse."""
        data = {"command": "python", "args": ["server.py"]}
        config = StdioServerConfig.model_validate(data)
        assert config.defer_loading is False


class TestRemoteServerConfigDeferLoading:
    """Tests for defer_loading on RemoteServerConfig."""

    def test_default_defer_loading(self) -> None:
        """Test that defer_loading defaults to False."""
        config = RemoteServerConfig(url="http://localhost:8080")
        assert config.defer_loading is False

    def test_defer_loading_true(self) -> None:
        """Test setting defer_loading to True."""
        config = RemoteServerConfig(url="http://localhost:8080", defer_loading=True)
        assert config.defer_loading is True

    def test_existing_fields_preserved(self) -> None:
        """Test that existing fields still work with defer_loading."""
        config = RemoteServerConfig(
            url="http://localhost:8080",
            headers={"Authorization": "Bearer token"},
            transport="sse",
            defer_loading=True,
        )
        assert config.url == "http://localhost:8080"
        assert config.headers == {"Authorization": "Bearer token"}
        assert config.transport == "sse"
        assert config.defer_loading is True

    def test_backward_compatible_without_defer_loading(self) -> None:
        """Test that configs without defer_loading still parse."""
        data = {"url": "http://localhost:8080"}
        config = RemoteServerConfig.model_validate(data)
        assert config.defer_loading is False


class TestConfigWithToolDiscovery:
    """Tests for tool_discovery field on Config model."""

    @pytest.fixture
    def minimal_config_data(self) -> dict[str, Any]:
        """Return minimal valid config data."""
        return {
            "clients": {"openai": {"provider": "openai"}},
            "models": {"test-model": {"client": "openai", "model": "gpt-4"}},
            "servers": {"test": {"command": "python", "args": ["server.py"]}},
        }

    def test_config_without_tool_discovery(self, minimal_config_data: dict[str, Any]) -> None:
        """Test that existing configs without tool_discovery still parse."""
        config = Config.model_validate(minimal_config_data)
        assert config.tool_discovery is None

    def test_config_with_tool_discovery(self, minimal_config_data: dict[str, Any]) -> None:
        """Test config with tool_discovery section."""
        minimal_config_data["tool_discovery"] = {
            "enabled": True,
            "defer_all": False,
            "max_search_results": 10,
        }
        config = Config.model_validate(minimal_config_data)
        assert config.tool_discovery is not None
        assert config.tool_discovery.enabled is True
        assert config.tool_discovery.defer_all is False
        assert config.tool_discovery.max_search_results == 10

    def test_config_with_empty_tool_discovery(self, minimal_config_data: dict[str, Any]) -> None:
        """Test config with empty tool_discovery dict uses all defaults."""
        minimal_config_data["tool_discovery"] = {}
        config = Config.model_validate(minimal_config_data)
        assert config.tool_discovery is not None
        assert config.tool_discovery.enabled is False
        assert config.tool_discovery.defer_all is False
        assert config.tool_discovery.max_search_results == 5

    def test_config_with_partial_tool_discovery(self, minimal_config_data: dict[str, Any]) -> None:
        """Test config with partial tool_discovery (uses defaults)."""
        minimal_config_data["tool_discovery"] = {"enabled": True}
        config = Config.model_validate(minimal_config_data)
        assert config.tool_discovery is not None
        assert config.tool_discovery.enabled is True
        assert config.tool_discovery.defer_all is False
        assert config.tool_discovery.max_search_results == 5

    def test_config_with_defer_loading_servers(self, minimal_config_data: dict[str, Any]) -> None:
        """Test config with servers using defer_loading."""
        minimal_config_data["servers"] = {
            "eager-server": {"command": "python", "args": ["eager.py"]},
            "deferred-server": {
                "command": "python",
                "args": ["deferred.py"],
                "defer_loading": True,
            },
            "remote-deferred": {
                "url": "http://localhost:9090",
                "defer_loading": True,
            },
        }
        minimal_config_data["tool_discovery"] = {"enabled": True}

        config = Config.model_validate(minimal_config_data)

        # Check eager server
        eager = config.servers["eager-server"]
        assert isinstance(eager, StdioServerConfig)
        assert eager.defer_loading is False

        # Check deferred stdio server
        deferred = config.servers["deferred-server"]
        assert isinstance(deferred, StdioServerConfig)
        assert deferred.defer_loading is True

        # Check deferred remote server
        remote = config.servers["remote-deferred"]
        assert isinstance(remote, RemoteServerConfig)
        assert remote.defer_loading is True

    def test_full_config_json_roundtrip(self, minimal_config_data: dict[str, Any]) -> None:
        """Test that a full config with tool_discovery round-trips through JSON."""
        minimal_config_data["tool_discovery"] = {
            "enabled": True,
            "defer_all": True,
            "max_search_results": 15,
        }
        minimal_config_data["servers"]["deferred"] = {
            "command": "node",
            "args": ["index.js"],
            "defer_loading": True,
        }

        config = Config.model_validate(minimal_config_data)
        json_str = config.model_dump_json()
        restored = Config.model_validate_json(json_str)

        assert restored.tool_discovery is not None
        assert restored.tool_discovery.enabled is True
        assert restored.tool_discovery.defer_all is True
        assert restored.tool_discovery.max_search_results == 15

        deferred = restored.servers["deferred"]
        assert isinstance(deferred, StdioServerConfig)
        assert deferred.defer_loading is True

    def test_config_json_file_backward_compat(self, tmp_path: Path) -> None:
        """Test that loading a config JSON file without tool_discovery works."""
        config_data = {
            "clients": {"openai": {"provider": "openai"}},
            "models": {"gpt4": {"client": "openai", "model": "gpt-4"}},
            "servers": {
                "my-server": {"command": "python", "args": ["server.py"]},
            },
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        loaded = json.loads(config_file.read_text())
        config = Config.model_validate(loaded)

        assert config.tool_discovery is None
        server = config.servers["my-server"]
        assert isinstance(server, StdioServerConfig)
        assert server.defer_loading is False

    def test_config_json_file_with_tool_discovery(self, tmp_path: Path) -> None:
        """Test loading a config JSON file that includes tool_discovery."""
        config_data = {
            "clients": {"openai": {"provider": "openai"}},
            "models": {"gpt4": {"client": "openai", "model": "gpt-4"}},
            "servers": {
                "eager": {"command": "python", "args": ["eager.py"]},
                "deferred": {
                    "url": "http://remote:8080",
                    "defer_loading": True,
                },
            },
            "tool_discovery": {
                "enabled": True,
                "max_search_results": 8,
            },
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        loaded = json.loads(config_file.read_text())
        config = Config.model_validate(loaded)

        assert config.tool_discovery is not None
        assert config.tool_discovery.enabled is True
        assert config.tool_discovery.max_search_results == 8
        assert config.tool_discovery.defer_all is False

        deferred = config.servers["deferred"]
        assert isinstance(deferred, RemoteServerConfig)
        assert deferred.defer_loading is True
