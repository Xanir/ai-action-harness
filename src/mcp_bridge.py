"""
Infrastructure Pre-Flight Checks
=================================

Async parallel connection verification for host-native MCP servers
exposed over SSE.  Provides a fail-fast dependency validator that
allows LangGraph actions to bail out early when a required service
is unreachable, while tolerating optional-service outages.

This module is used by ``src/harness.py`` during the container startup
sequence.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


MCP_REGISTRY_PATH = Path("config/mcp_registry.yaml")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPRegistry:
    """Immutable snapshot of the MCP server configuration.

    Created once at startup via :func:`load_mcp_registry`.
    Each server entry contains ``transport``, ``url``, and an optional
    ``prompt`` that describes the server's intended purpose for use in
     prompting an AI to build a tool call to an MCP server.
    """

    servers: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def server_names(self) -> list[str]:
        """Return the list of registered MCP server names."""
        return list(self.servers.keys())

    def get_server(self, name: str) -> dict[str, str]:
        """Look up a server's full configuration by name."""
        if name not in self.servers:
            raise KeyError(f"Unknown MCP server '{name}'.")
        return self.servers[name]

    def get_prompt(self, name: str) -> str | None:
        """Return the *prompt* for *name*, or ``None`` if not defined."""
        return self.get_server(name).get("prompt")


def load_mcp_registry(
    config_path: str | Path = MCP_REGISTRY_PATH,
) -> MCPRegistry:
    """Parse the MCP registry YAML file and return a frozen snapshot.

    Expected YAML shape::

        mcpServers:
          codegraph_mcp:
            transport: "sse"
            url: "http://..."
            prompt: >
              Multi-line description of this server's purpose.

    Parameters
    ----------
    config_path:
        Path to the YAML registry file.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"MCP registry not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    servers_raw: dict[str, dict[str, str]] = raw.get("mcpServers", {})
    if not isinstance(servers_raw, dict):
        raise ValueError(
            f"Expected 'mcpServers' to be a mapping, got {type(servers_raw).__name__}"
        )

    logger.info(
        "Loaded MCP registry: %d server(s) — %s.",
        len(servers_raw),
        ", ".join(sorted(servers_raw)) if servers_raw else "(none)",
    )

    return MCPRegistry(servers=servers_raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def connect_mcp_server(
    server_name: str,
    transport: str,
    url: str,
) -> list:
    """Create a single-server ``MultiServerMCPClient`` and hydrate its tools."""
    client_config = {server_name: {"transport": transport, "url": url}}
    logger.info("Connecting to MCP server '%s' at %s", server_name, url)
    client = MultiServerMCPClient(client_config)
    tools = await client.get_tools()
    logger.info("Hydrated %d tool(s) from '%s'", len(tools), server_name)
    for tool in tools:
        name = getattr(tool, "name", "<unnamed>")
        description = getattr(tool, "description", "<no description>")
        logger.info("  • %s — %s", name, description)
    return tools


async def connect_to_mcp_servers(
    registry: MCPRegistry,
) -> dict[str, tuple[bool, list | None]]:
    """Connect to every server registered in *registry* **in parallel**.

    Each server is given its own ``MultiServerMCPClient`` instance (via
    :func:`~src.mcp_harness.mcp_bridge.connect_mcp_server`) so that the
    SSE handshake and ``tools/list`` JSON-RPC call can run concurrently
    across all configured endpoints.

    Parameters
    ----------
    registry:
        The :class:`MCPRegistry` snapshot loaded from the YAML config.

    Returns
    -------
    dict[str, tuple[bool, list | None]]
        A mapping of ``server_name → (is_available, tools | None)``.
        Successful entries contain the hydrated tool list; failed entries
        contain ``None`` in the tools position.
    """
    servers = registry.servers

    tasks = {
        name: connect_mcp_server(name, entry["transport"], entry["url"])
        for name, entry in servers.items()
    }

    results: dict[str, tuple[bool, list | None]] = {}
    gathered = await _gather_ordered(tasks)

    for name, outcome in gathered.items():
        if isinstance(outcome, Exception):
            logger.warning("[%s] connection Failed — %s", name, outcome)
            results[name] = (False, None)
        else:
            logger.info("[%s] connection Successful (%d tools)", name, len(outcome))
            results[name] = (True, outcome)

    success_count = sum(1 for ok, _ in results.values() if ok)
    total = len(results)
    logger.info(
        "Infrastructure summary: %d/%d services available.", success_count, total
    )

    return results


def validate_action_dependencies(
    registry: MCPRegistry,
    infrastructure_status: dict[str, tuple[bool, Any]],
) -> None:
    """Fail-fast if any server registered in *registry* is marked as
    unavailable.

    Every server in the registry is considered required.  Servers that
    appear in *infrastructure_status* but are **not** in the registry
    only produce a warning — they do not block execution.

    Parameters
    ----------
    registry:
        The :class:`MCPRegistry` snapshot loaded from the YAML config.
    infrastructure_status:
        The mapping returned by :func:`connect_to_mcp_servers`.

    Raises
    ------
    RuntimeError
        If at least one registered server has a ``False`` status.  The
        message names every failing required server.
    """
    required = registry.server_names

    for name in required:
        if name not in infrastructure_status:
            raise RuntimeError(
                f"Required service '{name}' was not present in the "
                f"infrastructure check results.  Available: "
                f"{sorted(infrastructure_status)}"
            )

    failed_required = [name for name in required if not infrastructure_status[name][0]]

    if failed_required:
        raise RuntimeError(
            "The following required MCP services are DOWN: "
            f"{', '.join(failed_required)}.  Aborting action."
        )

    optional_servers = set(infrastructure_status) - set(required)
    for name in sorted(optional_servers):
        if not infrastructure_status[name][0]:
            logger.warning(
                "Optional service '%s' is unavailable — continuing without it.",
                name,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _gather_ordered(
    tasks: dict[str, Any],
) -> dict[str, Any]:
    """Run *tasks* concurrently and return results keyed by the original names."""
    names = list(tasks)
    coros = [tasks[n] for n in names]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)
    return dict(zip(names, outcomes))
