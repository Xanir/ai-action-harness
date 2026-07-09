"""
ai-action-harness — Server Entry Point
=======================================

Runs the harness startup sequence (AI health checks, MCP connections,
dependency validation) and then starts the FastAPI web server.

The web server keeps the process alive — no manual keep-alive loop
is needed.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import uvicorn

from src.harness import run_startup_checks
from src.webserver import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("server")


async def main() -> None:
    """Run harness startup checks, then launch the web server."""
    # ── Phase 0–3: AI health checks + MCP connections + validation ────
    mcp_status = await run_startup_checks()
    if mcp_status is None:
        logger.critical("Harness startup failed — aborting.")
        sys.exit(1)

    # ── Phase 4: build and run the web server ──────────────────────────
    logger.info("Starting web server on http://0.0.0.0:8080 ...")
    app = create_app(mcp_status)

    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_config=None)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
