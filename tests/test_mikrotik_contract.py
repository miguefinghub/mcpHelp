from __future__ import annotations

import json

import pytest

from mcp_help.servers.mikrotik.config import ConfigError, load_config
from mcp_help.servers.mikrotik.server import build_tools


def test_config_requires_core_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MIKROTIK_HOST", "MIKROTIK_USER", "MIKROTIK_PASSWORD", "MIKROTIK_PORT"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigError, match="MIKROTIK_HOST"):
        load_config()


def test_config_loads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROTIK_HOST", "192.168.88.1")
    monkeypatch.setenv("MIKROTIK_USER", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.setenv("MIKROTIK_PORT", "2222")

    config = load_config()

    assert config.host == "192.168.88.1"
    assert config.username == "admin"
    assert config.password == "secret"
    assert config.port == 2222


def test_config_loads_explicit_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MIKROTIK_HOST", "MIKROTIK_USER", "MIKROTIK_PASSWORD", "MIKROTIK_PORT"):
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / "mikrotik.env"
    env_file.write_text(
        "\n".join(
            [
                'MIKROTIK_HOST="10.0.0.1"',
                'MIKROTIK_USER="admin"',
                'MIKROTIK_PASSWORD="p@ss word"',
                "MIKROTIK_PORT=2200",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_file)

    assert config.host == "10.0.0.1"
    assert config.username == "admin"
    assert config.password == "p@ss word"
    assert config.port == 2200


def test_config_fails_when_explicit_env_file_is_missing(tmp_path) -> None:
    with pytest.raises(ConfigError, match="Environment file not found"):
        load_config(tmp_path / "missing.env")


def test_tools_are_mikrotik_only() -> None:
    tool_names = {tool.name for tool in build_tools()}

    assert "mikrotik_execute_command" in tool_names
    assert "mikrotik_create_backup" in tool_names
    assert "mikrotik_torch" in tool_names
    assert not any("wireshark" in name.lower() for name in tool_names)
    assert not any("capture" in name.lower() for name in tool_names)


def test_tool_schemas_are_json_serializable() -> None:
    for tool in build_tools():
        json.dumps(tool.inputSchema)
