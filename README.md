# MCP Help

Repository for simple, cloneable MCP servers that are easy to configure from VS Code / GitHub Copilot.

The first included server is `mikrotik`: a stdio MCP server for RouterOS SSH debugging, backups, and basic configuration. It intentionally does not include Wireshark or complex discovery logic.

## Quick Start

On a remote PC:

```powershell
git clone https://github.com/miguefinghub/mcpHelp.git
cd MCP_Help
.\install.ps1
code .
```

`install.ps1` is the single entry point. It performs the full setup:

- Detects an existing local installation and asks whether to reinstall/reconfigure from zero.
- Removes `.venv`, `.mcp-local`, and `.vscode/mcp.json` when reconfiguration is confirmed.
- Prompts for router IP/host, SSH username, SSH password, and SSH port.
- Runs a ping check against the router for basic connectivity.
- Installs `uv` if it is missing.
- Creates `.venv` with Python 3.12 managed by `uv`.
- Installs the package and dependencies.
- Writes `.mcp-local/mikrotik.env` with local MikroTik settings.
- Writes `.vscode/mcp.json` pointing to the MCP server.
- Checks VS Code / Copilot / MCP readiness when possible from the terminal.
- Validates SSH against the router.
- Runs a stdio MCP smoke test and the local tests.

## Local Configuration

The password is not stored in `.vscode/mcp.json`. It is stored in:

```text
.mcp-local/mikrotik.env
```

That directory is ignored by Git and is removed during reinstall/reconfiguration. The MCP server reads this file explicitly with `--env-file`; if it is missing or invalid, the server fails with a clear error.

## Requirements

- Windows with PowerShell.
- `winget` recommended if `uv` is not installed.
- VS Code with GitHub Copilot.
- MCP enabled/allowed in VS Code.
- Network access to the MikroTik router through ping and SSH.
- RouterOS user with enough permissions to read configuration and, if backup/configuration tools are used, to run `/system backup`, `/export`, `/file`, etc.

No global Python installation is required. `install.ps1` creates `.venv` with Python 3.12 managed by `uv`.

## VS Code / Copilot

After `.\install.ps1`:

1. Open the repository with `code .`.
2. Run `MCP: List Servers`.
3. Select `mikrotik`.
4. Confirm trust/enable when VS Code asks.
5. Use Copilot Chat in Agent mode.

VS Code stores server enable/disable and trust state outside `.vscode/mcp.json`, so the installer can check and warn, but the final confirmation must happen inside VS Code.

Relevant VS Code settings:

- `chat.mcp.access`: if set to `none`, MCP is blocked.
- `chat.mcp.autoStart`: if disabled, start the server manually with `MCP: List Servers`.

## Manual Validation

Validate SSH using the local configuration:

```powershell
.\.venv\Scripts\python.exe -m mcp_help.servers.mikrotik.server --env-file .\.mcp-local\mikrotik.env --validate
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## MikroTik Tools

- `mikrotik_execute_command`: execute one RouterOS command.
- `mikrotik_execute_commands`: execute several RouterOS commands in order.
- `mikrotik_system_summary`: collect identity, resources, routerboard info, addresses, interfaces, routes, and recent logs.
- `mikrotik_debug_snapshot`: collect a broad troubleshooting snapshot.
- `mikrotik_interfaces`: show interface details and statistics.
- `mikrotik_ip_addresses`: show IP addresses.
- `mikrotik_routes`: show routes.
- `mikrotik_dhcp_leases`: show DHCP leases.
- `mikrotik_firewall_filters`: show firewall filter rules.
- `mikrotik_logs`: show recent logs.
- `mikrotik_torch`: run traffic inspection on an interface for a few seconds.
- `mikrotik_create_backup`: create a binary backup and `.rsc` export, then download both to `backups/mikrotik/...`.
- `mikrotik_export_config`: export configuration to an `.rsc` file.
- `mikrotik_list_backups`: list local backup files.

## Error Policy

No fallbacks:

- If the `--env-file` path is missing, the server fails.
- If `MIKROTIK_HOST`, `MIKROTIK_USER`, or `MIKROTIK_PASSWORD` is missing, the server fails.
- SSH keys and the SSH agent are not used as silent alternatives.
- If ping fails during installation, installation stops.
- If SSH validation fails during installation, installation stops.
- If SFTP or a RouterOS command fails, the tool returns `ERROR:` with details.
- There is no automatic discovery or alternate routing.

## Structure

```text
mcp_help/
  servers/
    mikrotik/
      config.py
      routeros.py
      server.py
      ssh.py
```

To add another simple MCP server later, create another subpackage under `mcp_help/servers/<name>` and add a dedicated installer/configuration flow if it needs its own settings.
