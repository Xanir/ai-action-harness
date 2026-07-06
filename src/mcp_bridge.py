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
import json
import logging
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


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


async def check_infrastructure(
    config_path: str,
) -> dict[str, tuple[bool, list | None]]:
    """Connect to every MCP server defined in *config_path* **in parallel**.

    Each server is given its own ``MultiServerMCPClient`` instance (via
    :func:`~src.mcp_harness.mcp_bridge.connect_mcp_server`) so that the
    SSE handshake and ``tools/list`` JSON-RPC call can run concurrently
    across all configured endpoints.

    Parameters
    ----------
    config_path:
        Path to the JSON configuration file.  Expected shape::

            {
              "<server_name>": {
                "transport": "sse",
                "url": "<endpoint>"
              }
            }

    Returns
    -------
    dict[str, tuple[bool, list | None]]
        A mapping of ``server_name → (is_available, tools | None)``.
        Successful entries contain the hydrated tool list; failed entries
        contain ``None`` in the tools position.
    """
    servers: dict[str, dict[str, str]] = _load_json_config(Path(config_path))

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
    action_required_servers: list[str],
    infrastructure_status: dict[str, tuple[bool, Any]],
) -> None:
    """Fail-fast if any *required* server is marked as unavailable.

    Servers that are not in *action_required_servers* but happen to be
    down only produce a warning — they do not block execution.

    Parameters
    ----------
    action_required_servers:
        Names of MCP servers that the current action **must** have.
    infrastructure_status:
        The mapping returned by :func:`check_infrastructure`.

    Raises
    ------
    RuntimeError
        If at least one server in *action_required_servers* has a
        ``False`` status.  The message names every failing required
        server.
    """
    for name in action_required_servers:
        if name not in infrastructure_status:
            raise RuntimeError(
                f"Required service '{name}' was not present in the "
                f"infrastructure check results.  Available: "
                f"{sorted(infrastructure_status)}"
            )

    failed_required = [
        name for name in action_required_servers if not infrastructure_status[name][0]
    ]

    if failed_required:
        raise RuntimeError(
            "The following required MCP services are DOWN: "
            f"{', '.join(failed_required)}.  Aborting action."
        )

    optional_servers = set(infrastructure_status) - set(action_required_servers)
    for name in sorted(optional_servers):
        if not infrastructure_status[name][0]:
            logger.warning(
                "Optional service '%s' is unavailable — continuing without it.",
                name,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json_config(path: Path) -> dict[str, dict[str, str]]:
    """Read and validate the top-level JSON server map."""
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw: object = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Expected a JSON object at the top level, got {type(raw).__name__}"
        )
    return raw  # type: ignore[return-value]


async def _gather_ordered(
    tasks: dict[str, Any],
) -> dict[str, Any]:
    """Run *tasks* concurrently and return results keyed by the original names."""
    names = list(tasks)
    coros = [tasks[n] for n in names]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)
    return dict(zip(names, outcomes))
