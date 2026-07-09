"""
ai-action-harness — Startup Orchestration
==========================================

Orchestrates the full container startup sequence:

1. Load model and MCP registries (module-level)
2. Run parallel AI platform health checks
3. Run parallel MCP pre-flight connection checks
4. Validate that all required dependencies are healthy (fail-fast if not)

Returns the MCP infrastructure status so the webserver can use the
pre-connected tool lists.
"""

from __future__ import annotations

import logging

from src.ai_health import run_ai_health_checks
from src.mcp_bridge import (
    MCPRegistry,
    connect_to_mcp_servers,
    load_mcp_registry,
    validate_action_dependencies,
)
from src.models import ModelRegistry, load_model_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("harness")

# Sealed registries loaded once at module level — require reboot to change.
mcp_registry: MCPRegistry = load_mcp_registry()
model_registry: ModelRegistry = load_model_registry()


async def run_startup_checks() -> dict[str, tuple[bool, list | None]] | None:
    """Execute phases 0–3 of the harness startup sequence.

    Returns the MCP infrastructure status dict on success, or ``None``
    if AI health checks fail (caller should abort).
    """
    logger.info("=== ai-action-harness starting ===")

    # ── Phase 0: model registry (already loaded at module level) ───────
    logger.info(
        "Model registry: %d model(s), %d role(s).",
        len(model_registry.models),
        len(model_registry.roles),
    )

    # ── Phase 1: parallel AI platform health checks ────────────────────
    logger.info("Running AI platform health checks...")
    if not await run_ai_health_checks(model_registry):
        logger.critical("AI platform health checks failed — terminating harness.")
        return None

    # ── Phase 2: parallel MCP health check ──────────────────
    logger.info("Running infrastructure pre-flight checks...")
    status = await connect_to_mcp_servers(mcp_registry)

    # ── Phase 3: conditional fail-fast validation ──────────────────────
    logger.info("Validating required dependencies...")
    validate_action_dependencies(mcp_registry, status)
    logger.info("All required services are healthy.")

    return status
