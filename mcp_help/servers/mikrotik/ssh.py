from __future__ import annotations

import re
import time
from pathlib import Path

import paramiko


class RouterOSSSHError(RuntimeError):
    """Raised for SSH, command, or SFTP failures."""


class RouterOSSSHClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        connect_timeout: float = 8.0,
        command_timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self._client: paramiko.SSHClient | None = None
        self._shell: paramiko.Channel | None = None

    def __enter__(self) -> "RouterOSSSHClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def connect(self) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
            )
        except Exception as exc:
            raise RouterOSSSHError(
                f"SSH connection failed for {self.username}@{self.host}:{self.port}: {exc}"
            ) from exc
        self._client = client

    def close(self) -> None:
        if self._shell is not None:
            try:
                self._shell.close()
            except Exception:
                pass
            self._shell = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def execute(self, command: str, timeout: float | None = None) -> str:
        if self._client is None:
            raise RouterOSSSHError("SSH client is not connected")
        if not command.strip():
            raise RouterOSSSHError("RouterOS command cannot be empty")

        try:
            stdin, stdout, stderr = self._client.exec_command(
                command,
                timeout=timeout or self.command_timeout,
            )
            stdin.close()
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise RouterOSSSHError(f"RouterOS command failed: {command}: {exc}") from exc

        if error.strip() and not output.strip():
            raise RouterOSSSHError(f"RouterOS command returned stderr: {error.strip()}")

        return output.strip()

    def execute_shell(self, command: str, timeout: float | None = None) -> str:
        if self._client is None:
            raise RouterOSSSHError("SSH client is not connected")
        if not command.strip():
            raise RouterOSSSHError("RouterOS command cannot be empty")

        shell = self._get_shell()
        try:
            shell.send(command + "\n")
            return self._read_until_prompt(shell, timeout or self.command_timeout)
        except Exception as exc:
            raise RouterOSSSHError(f"RouterOS shell command failed: {command}: {exc}") from exc

    def download(self, remote_path: str, local_path: Path) -> None:
        if self._client is None:
            raise RouterOSSSHError("SSH client is not connected")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.open_sftp() as sftp:
                sftp.get(remote_path, str(local_path))
        except Exception as exc:
            raise RouterOSSSHError(
                f"SFTP download failed from {remote_path} to {local_path}: {exc}"
            ) from exc

    def upload(self, local_path: Path, remote_path: str) -> None:
        if self._client is None:
            raise RouterOSSSHError("SSH client is not connected")
        if not local_path.exists():
            raise RouterOSSSHError(f"Local file does not exist: {local_path}")
        try:
            with self._client.open_sftp() as sftp:
                sftp.put(str(local_path), remote_path)
        except Exception as exc:
            raise RouterOSSSHError(
                f"SFTP upload failed from {local_path} to {remote_path}: {exc}"
            ) from exc

    def _get_shell(self) -> paramiko.Channel:
        if self._client is None:
            raise RouterOSSSHError("SSH client is not connected")
        if self._shell is None or self._shell.closed:
            self._shell = self._client.invoke_shell(width=240, height=80)
            time.sleep(0.4)
            if self._shell.recv_ready():
                self._shell.recv(65535)
        return self._shell

    @staticmethod
    def _read_until_prompt(shell: paramiko.Channel, timeout: float) -> str:
        output = ""
        started_at = time.monotonic()
        prompt_pattern = re.compile(r"[\]>] ?$")
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        while time.monotonic() - started_at < timeout:
            if shell.recv_ready():
                output += shell.recv(65535).decode("utf-8", errors="replace")
                if prompt_pattern.search(output.strip()):
                    break
            else:
                time.sleep(0.1)

        clean = ansi_escape.sub("", output)
        lines = clean.splitlines()
        if len(lines) >= 2:
            lines = lines[1:-1]
        return "\n".join(lines).strip()

