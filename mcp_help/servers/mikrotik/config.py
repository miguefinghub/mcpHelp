from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MikroTikConfig:
    host: str
    username: str
    password: str
    port: int
    connect_timeout: float = 8.0
    command_timeout: float = 30.0


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _load_env_file(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        raise ConfigError(f"Environment file not found: {env_file}")

    values: dict[str, str] = {}
    for line_number, line in enumerate(env_file.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigError(f"Invalid environment file line {line_number}: missing '='")
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Invalid environment file line {line_number}: empty key")
        values[key] = _parse_env_value(value)
    return values


def _required_value(values: dict[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or value.strip() == "":
        raise ConfigError(f"Missing required environment variable: {name}")
    return value.strip()


def load_config(env_file: str | Path | None = None) -> MikroTikConfig:
    values = dict(os.environ)
    if env_file is not None:
        values.update(_load_env_file(Path(env_file)))

    port_raw = values.get("MIKROTIK_PORT", "22").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ConfigError("MIKROTIK_PORT must be an integer") from exc

    if port < 1 or port > 65535:
        raise ConfigError("MIKROTIK_PORT must be between 1 and 65535")

    return MikroTikConfig(
        host=_required_value(values, "MIKROTIK_HOST"),
        username=_required_value(values, "MIKROTIK_USER"),
        password=_required_value(values, "MIKROTIK_PASSWORD"),
        port=port,
    )
