from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable

from .config import MikroTikConfig
from .ssh import RouterOSSSHClient


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "unknown"


def _routeros_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class RouterOSAgent:
    def __init__(self, config: MikroTikConfig, backup_root: Path | None = None) -> None:
        self.config = config
        self.backup_root = backup_root or Path.cwd() / "backups" / "mikrotik"

    def _client(
        self,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        port: int | None = None,
    ) -> RouterOSSSHClient:
        return RouterOSSSHClient(
            host=host or self.config.host,
            username=username or self.config.username,
            password=password if password is not None else self.config.password,
            port=port or self.config.port,
            connect_timeout=self.config.connect_timeout,
            command_timeout=self.config.command_timeout,
        )

    def validate(self) -> str:
        return self.execute_command("/system identity print")

    def execute_command(
        self,
        command: str,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        port: int | None = None,
    ) -> str:
        with self._client(host, username, password, port) as client:
            return client.execute(command)

    def execute_commands(
        self,
        commands: Iterable[str],
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        port: int | None = None,
        stop_on_error: bool = True,
    ) -> str:
        results: list[str] = []
        with self._client(host, username, password, port) as client:
            for index, command in enumerate(commands, start=1):
                try:
                    output = client.execute(command)
                    results.append(f"[{index}] {command}\n{output}")
                except Exception as exc:
                    results.append(f"[{index}] {command}\nERROR: {exc}")
                    if stop_on_error:
                        break
        return "\n\n".join(results)

    def system_summary(self, **kwargs: object) -> str:
        return self.execute_commands(
            [
                "/system identity print",
                "/system resource print",
                "/system routerboard print",
                "/ip address print",
                "/interface print where running=yes",
                "/ip route print",
                "/log print without-paging",
            ],
            **kwargs,
            stop_on_error=False,
        )

    def debug_snapshot(self, **kwargs: object) -> str:
        return self.execute_commands(
            [
                "/system identity print",
                "/system resource print",
                "/system package print",
                "/system routerboard print",
                "/interface print detail without-paging",
                "/interface bridge print detail without-paging",
                "/interface bridge port print detail without-paging",
                "/ip address print detail without-paging",
                "/ip route print detail without-paging",
                "/ip arp print detail without-paging",
                "/ip dhcp-server print detail without-paging",
                "/ip dhcp-server lease print detail without-paging",
                "/ip dns print",
                "/ip firewall filter print detail without-paging",
                "/ip firewall nat print detail without-paging",
                "/interface wireguard print detail without-paging",
                "/interface wireguard peers print detail without-paging",
                "/log print without-paging",
            ],
            **kwargs,
            stop_on_error=False,
        )

    def interfaces(self, **kwargs: object) -> str:
        return self.execute_commands(
            [
                "/interface print detail without-paging",
                "/interface print stats without-paging",
            ],
            **kwargs,
            stop_on_error=False,
        )

    def ip_addresses(self, **kwargs: object) -> str:
        return self.execute_command("/ip address print detail without-paging", **kwargs)

    def routes(self, **kwargs: object) -> str:
        return self.execute_command("/ip route print detail without-paging", **kwargs)

    def dhcp_leases(self, **kwargs: object) -> str:
        return self.execute_command(
            "/ip dhcp-server lease print detail without-paging",
            **kwargs,
        )

    def firewall_filters(self, **kwargs: object) -> str:
        return self.execute_command(
            "/ip firewall filter print detail without-paging",
            **kwargs,
        )

    def logs(self, **kwargs: object) -> str:
        return self.execute_command("/log print without-paging", **kwargs)

    def torch(
        self,
        interface: str,
        duration: int = 5,
        src_address: str | None = None,
        dst_address: str | None = None,
        port_filter: str | None = None,
        protocol: str | None = None,
        **kwargs: object,
    ) -> str:
        parts = [
            "/tool torch",
            f"interface={interface}",
            f"duration={duration}s",
            "freeze-frame-interval=1",
        ]
        if src_address:
            parts.append(f"src-address={src_address}")
        if dst_address:
            parts.append(f"dst-address={dst_address}")
        if port_filter:
            parts.append(f"port={port_filter}")
        if protocol:
            parts.append(f"ip-protocol={protocol}")
        return self.execute_command(" ".join(parts), **kwargs)

    def create_backup(
        self,
        backup_password: str | None = None,
        include_export: bool = True,
        **kwargs: object,
    ) -> str:
        host = str(kwargs.get("host") or self.config.host)
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        base_name = f"mcp-backup-{timestamp}"
        backup_remote = f"{base_name}.backup"
        export_remote = f"{base_name}.rsc"

        with self._client(
            kwargs.get("host") if isinstance(kwargs.get("host"), str) else None,
            kwargs.get("username") if isinstance(kwargs.get("username"), str) else None,
            kwargs.get("password") if isinstance(kwargs.get("password"), str) else None,
            kwargs.get("port") if isinstance(kwargs.get("port"), int) else None,
        ) as client:
            router_info = self._router_info(client)
            target_dir = self._router_backup_dir(host, router_info)

            backup_cmd = f"/system backup save name={_routeros_quote(base_name)}"
            if backup_password:
                backup_cmd += f" password={_routeros_quote(backup_password)}"
            client.execute(backup_cmd, timeout=60)
            local_backup = target_dir / backup_remote
            client.download(backup_remote, local_backup)

            outputs = {
                "backup": str(local_backup),
                "export": None,
                "router": router_info,
            }

            if include_export:
                client.execute(f"/export file={_routeros_quote(base_name)}", timeout=60)
                local_export = target_dir / export_remote
                client.download(export_remote, local_export)
                outputs["export"] = str(local_export)

            self._remove_remote_file(client, backup_remote)
            if include_export:
                self._remove_remote_file(client, export_remote)

        return json.dumps(outputs, indent=2)

    def export_config(
        self,
        include_sensitive: bool = False,
        **kwargs: object,
    ) -> str:
        host = str(kwargs.get("host") or self.config.host)
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        base_name = f"mcp-export-{timestamp}"
        remote_file = f"{base_name}.rsc"

        with self._client(
            kwargs.get("host") if isinstance(kwargs.get("host"), str) else None,
            kwargs.get("username") if isinstance(kwargs.get("username"), str) else None,
            kwargs.get("password") if isinstance(kwargs.get("password"), str) else None,
            kwargs.get("port") if isinstance(kwargs.get("port"), int) else None,
        ) as client:
            router_info = self._router_info(client)
            target_dir = self._router_backup_dir(host, router_info)
            prefix = "/export show-sensitive" if include_sensitive else "/export"
            client.execute(f"{prefix} file={_routeros_quote(base_name)}", timeout=60)
            local_path = target_dir / remote_file
            client.download(remote_file, local_path)
            self._remove_remote_file(client, remote_file)

        return str(local_path)

    def list_backups(self, host: str | None = None) -> str:
        if not self.backup_root.exists():
            return "[]"
        files = []
        host_marker = _safe_name(host) if host else None
        for path in sorted(self.backup_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".backup", ".rsc"}:
                rel = path.relative_to(self.backup_root)
                if host_marker is None or host_marker in str(rel):
                    files.append(str(rel))
        return json.dumps(files, indent=2)

    def _router_info(self, client: RouterOSSSHClient) -> dict[str, str]:
        identity = self._extract_value(client.execute("/system identity print"), "name")
        routerboard = client.execute("/system routerboard print")
        return {
            "identity": identity or "unknown",
            "model": self._extract_value(routerboard, "model") or "unknown",
            "serial": self._extract_value(routerboard, "serial-number") or "unknown",
        }

    def _router_backup_dir(self, host: str, router_info: dict[str, str]) -> Path:
        dirname = "-".join(
            [
                _safe_name(router_info.get("serial", "unknown")),
                _safe_name(router_info.get("identity", "unknown")),
                _safe_name(host),
            ]
        )
        target = self.backup_root / dirname
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _extract_value(output: str, key: str) -> str | None:
        pattern = re.compile(rf"(?:^|\s){re.escape(key)}:\s*(.+)$")
        for line in output.splitlines():
            match = pattern.search(line.strip())
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _remove_remote_file(client: RouterOSSSHClient, filename: str) -> None:
        client.execute(f"/file remove [find name={_routeros_quote(filename)}]")

