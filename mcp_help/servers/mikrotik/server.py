from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any, Callable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import ConfigError, load_config
from .routeros import RouterOSAgent

LOGGER = logging.getLogger("mcp_help.mikrotik")


def _target_fields() -> dict[str, Any]:
    return {
        "host": {
            "type": "string",
            "description": "Optional target router host. Defaults to MIKROTIK_HOST.",
        },
        "username": {
            "type": "string",
            "description": "Optional SSH username. Defaults to MIKROTIK_USER.",
        },
        "password": {
            "type": "string",
            "description": "Optional SSH password. Defaults to MIKROTIK_PASSWORD.",
        },
        "port": {
            "type": "integer",
            "description": "Optional SSH port. Defaults to MIKROTIK_PORT.",
        },
    }


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    merged = {**properties, **_target_fields()}
    return {
        "type": "object",
        "properties": merged,
        "required": required or [],
        "additionalProperties": False,
    }


def build_tools() -> list[Tool]:
    return [
        Tool(
            name="mikrotik_execute_command",
            description="Execute one RouterOS command over SSH.",
            inputSchema=_schema(
                {
                    "command": {
                        "type": "string",
                        "description": "RouterOS command, for example /system identity print.",
                    }
                },
                ["command"],
            ),
        ),
        Tool(
            name="mikrotik_execute_commands",
            description="Execute RouterOS commands in order over one SSH session.",
            inputSchema=_schema(
                {
                    "commands": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "stop_on_error": {
                        "type": "boolean",
                        "description": "Stop at first command failure. Default true.",
                    },
                },
                ["commands"],
            ),
        ),
        Tool(
            name="mikrotik_system_summary",
            description="Collect identity, resources, routerboard, addresses, running interfaces, routes, and logs.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_debug_snapshot",
            description="Collect a broad read-only RouterOS snapshot for troubleshooting.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_interfaces",
            description="Show interface details and statistics.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_ip_addresses",
            description="Show IP address configuration.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_routes",
            description="Show IP routes.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_dhcp_leases",
            description="Show DHCP server leases.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_firewall_filters",
            description="Show firewall filter rules.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_logs",
            description="Show RouterOS logs without paging.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="mikrotik_torch",
            description="Run RouterOS torch on an interface for short traffic debugging.",
            inputSchema=_schema(
                {
                    "interface": {"type": "string"},
                    "duration": {
                        "type": "integer",
                        "description": "Duration in seconds. Default 5.",
                    },
                    "src_address": {"type": "string"},
                    "dst_address": {"type": "string"},
                    "port_filter": {"type": "string"},
                    "protocol": {"type": "string"},
                },
                ["interface"],
            ),
        ),
        Tool(
            name="mikrotik_create_backup",
            description="Create a RouterOS binary backup and optional .rsc export, then download to backups/mikrotik.",
            inputSchema=_schema(
                {
                    "backup_password": {
                        "type": "string",
                        "description": "Optional RouterOS backup password.",
                    },
                    "include_export": {
                        "type": "boolean",
                        "description": "Also create and download an .rsc export. Default true.",
                    },
                }
            ),
        ),
        Tool(
            name="mikrotik_export_config",
            description="Export RouterOS configuration to a local .rsc file.",
            inputSchema=_schema(
                {
                    "include_sensitive": {
                        "type": "boolean",
                        "description": "Use /export show-sensitive. Default false.",
                    }
                }
            ),
        ),
        Tool(
            name="mikrotik_list_backups",
            description="List local MikroTik backup/export files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Optional host filter.",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
    ]


def _target_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for key in ("host", "username", "password", "port"):
        if key in arguments and arguments[key] not in (None, ""):
            kwargs[key] = arguments[key]
    return kwargs


def build_handlers(agent: RouterOSAgent) -> dict[str, Callable[[dict[str, Any]], str]]:
    return {
        "mikrotik_execute_command": lambda args: agent.execute_command(
            args["command"],
            **_target_kwargs(args),
        ),
        "mikrotik_execute_commands": lambda args: agent.execute_commands(
            args["commands"],
            stop_on_error=args.get("stop_on_error", True),
            **_target_kwargs(args),
        ),
        "mikrotik_system_summary": lambda args: agent.system_summary(**_target_kwargs(args)),
        "mikrotik_debug_snapshot": lambda args: agent.debug_snapshot(**_target_kwargs(args)),
        "mikrotik_interfaces": lambda args: agent.interfaces(**_target_kwargs(args)),
        "mikrotik_ip_addresses": lambda args: agent.ip_addresses(**_target_kwargs(args)),
        "mikrotik_routes": lambda args: agent.routes(**_target_kwargs(args)),
        "mikrotik_dhcp_leases": lambda args: agent.dhcp_leases(**_target_kwargs(args)),
        "mikrotik_firewall_filters": lambda args: agent.firewall_filters(**_target_kwargs(args)),
        "mikrotik_logs": lambda args: agent.logs(**_target_kwargs(args)),
        "mikrotik_torch": lambda args: agent.torch(
            interface=args["interface"],
            duration=args.get("duration", 5),
            src_address=args.get("src_address"),
            dst_address=args.get("dst_address"),
            port_filter=args.get("port_filter"),
            protocol=args.get("protocol"),
            **_target_kwargs(args),
        ),
        "mikrotik_create_backup": lambda args: agent.create_backup(
            backup_password=args.get("backup_password"),
            include_export=args.get("include_export", True),
            **_target_kwargs(args),
        ),
        "mikrotik_export_config": lambda args: agent.export_config(
            include_sensitive=args.get("include_sensitive", False),
            **_target_kwargs(args),
        ),
        "mikrotik_list_backups": lambda args: agent.list_backups(host=args.get("host")),
    }


async def serve(env_file: str | None = None) -> None:
    config = load_config(env_file)
    agent = RouterOSAgent(config)
    tools = build_tools()
    handlers = build_handlers(agent)
    server = Server("mcp-help-mikrotik")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in handlers:
            return [TextContent(type="text", text=f"ERROR: Unknown tool: {name}")]
        try:
            result = handlers[name](arguments or {})
        except Exception as exc:
            LOGGER.exception("Tool failed: %s", name)
            result = f"ERROR: {exc}"
        return [TextContent(type="text", text=str(result))]

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Help MikroTik server")
    parser.add_argument("--validate", action="store_true", help="Validate SSH connectivity and exit")
    parser.add_argument("--env-file", help="Path to the MikroTik environment file")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        if args.validate:
            config = load_config(args.env_file)
            result = RouterOSAgent(config).validate()
            print(result)
            return

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(serve(args.env_file))
    except ConfigError as exc:
        LOGGER.error("%s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        LOGGER.exception("Server failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
