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

from src.mcp_bridge import check_infrastructure, validate_action_dependencies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("harness")

CONFIG_PATH = "config/mcp_wrappers.config.json"
REQUIRED_SERVERS = ["codegraph_mcp"]


async def main() -> None:
    logger.info("=== ai-action-harness starting ===")

    # ── Phase 1: parallel infrastructure health check ──────────────────
    logger.info("Running infrastructure pre-flight checks...")
    status = await check_infrastructure(CONFIG_PATH)

    # ── Phase 2: conditional fail-fast validation ──────────────────────
    logger.info("Validating required dependencies...")
    validate_action_dependencies(REQUIRED_SERVERS, status)
    logger.info("All required services are healthy.")

    # ── Phase 3: keep the container alive ──────────────────────────────
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
