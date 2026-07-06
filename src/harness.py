"""
ai-action-harness — Startup Entry Point
=======================================

Orchestrates the full container startup sequence:

1. Read MCP wrapper configuration from ``config/mcp_wrappers.config.json``
2. Run parallel pre-flight connection checks against every registered server
3. Validate that all *required* dependencies are healthy (fail-fast if not)
4. Keep the container alive for downstream LangGraph orchestration
"""

from __future__ import annotations

import asyncio
import logging
import signal

from src.ai_health import run_ai_health_checks
from src.mcp_bridge import check_infrastructure, validate_action_dependencies
from src.models import ModelRegistry, load_model_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("harness")

CONFIG_PATH = "config/mcp_wrappers.config.json"
REQUIRED_SERVERS = ["codegraph_mcp"]

# Sealed registry loaded once at module level — requires reboot to change.
model_registry: ModelRegistry = load_model_registry()


async def main() -> None:
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
        return

    # ── Phase 2: parallel infrastructure health check ──────────────────
    logger.info("Running infrastructure pre-flight checks...")
    status = await check_infrastructure(CONFIG_PATH)

    # ── Phase 3: conditional fail-fast validation ──────────────────────
    logger.info("Validating required dependencies...")
    validate_action_dependencies(REQUIRED_SERVERS, status)
    logger.info("All required services are healthy.")

    # ── Phase 4: keep the container alive ──────────────────────────────
    logger.info("Startup complete — waiting for orchestration requests.")
    stop_event = asyncio.Event()

    def _handle_signal(signum: int) -> None:
        logger.info("Received signal %d, shutting down.", signum)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    await stop_event.wait()
    logger.info("ai-action-harness stopped.")


if __name__ == "__main__":
    asyncio.run(main())
