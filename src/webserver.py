"""
FastAPI Web Server
==================

Serves the Vue frontend and exposes endpoints for MCP server discovery
and tool invocation.  Accepts pre-connected MCP tool lists from the
harness startup sequence so the API never needs to connect on its own.

The AI Harness prompt endpoint is scaffolded but disabled until the
LangGraph orchestration layer is ready.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.mcp_bridge import load_mcp_registry

logger = logging.getLogger(__name__)

# LangChain Runnable-internal fields that should never appear as user-facing
# tool parameters.
_RUNNABLE_FIELDS = frozenset(
    {
        "config",
        "callbacks",
        "tags",
        "metadata",
        "run_name",
        "run_id",
    }
)


def _extract_args_schema(tool: Any) -> dict | None:
    """Return a JSON Schema for the tool's user-visible parameters, or None."""
    if not hasattr(tool, "args_schema") or tool.args_schema is None:
        return None

    raw = tool.args_schema
    # langchain_mcp_adapters stores the schema as a plain dict; vanilla
    # LangChain StructuredTool uses a Pydantic model.
    if hasattr(raw, "model_json_schema"):
        raw = raw.model_json_schema()

    properties = raw.get("properties", {})
    required = raw.get("required", [])

    # Strip Runnable-internal fields so the frontend only shows real args.
    user_props = {k: v for k, v in properties.items() if k not in _RUNNABLE_FIELDS}
    user_required = [k for k in required if k in user_props]

    if not user_props:
        return None

    return {
        "type": "object",
        "properties": user_props,
        "required": user_required,
    }


# ---------------------------------------------------------------------------
# Application state (populated by create_app)
# ---------------------------------------------------------------------------

_mcp_clients: dict[str, Any] = {}
"""Live MCP tool lists, keyed by server name (tools carry client references)."""

_mcp_tools: dict[str, list[dict[str, Any]]] = {}
"""Cached tool metadata: {server_name: [{name, description, args_schema}, ...]}."""


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Minimal lifespan — tools are already connected by the harness."""
    logger.info("Web server ready (MCP tools provided by harness).")
    yield
    logger.info("Web server shutting down.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    mcp_status: dict[str, tuple[bool, list | None]] | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Parameters
    ----------
    mcp_status:
        The infrastructure status dict returned by
        :func:`src.harness.run_startup_checks`.  Maps server name to
        ``(is_available, tools | None)``.  Tools that are ``None`` or
        unavailable are stored as empty lists.
    """
    # ── Populate MCP state from harness results ────────────────────────
    if mcp_status:
        for name, (ok, tools) in mcp_status.items():
            if ok and tools:
                _mcp_clients[name] = tools
                _mcp_tools[name] = [
                    {
                        "name": getattr(t, "name", "<unnamed>"),
                        "description": getattr(t, "description", ""),
                        "args_schema": _extract_args_schema(t),
                    }
                    for t in tools
                ]
            else:
                _mcp_tools[name] = []
        logger.info(
            "Initialised %d MCP server(s) from harness.",
            len(_mcp_clients),
        )

    app = FastAPI(
        title="AI Action Harness",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API routes ───────────────────────────────────────────────────
    app.include_router(router)

    # ── Serve Vue production build ────────────────────────────────────
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


# ── Request / response models ──────────────────────────────────────────────


class MCPServerInfo(BaseModel):
    name: str
    prompt: str | None
    transport: str
    url: str
    tools: list[dict[str, Any]]


class MCPCallRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: dict[str, Any] = {}


class MCPCallResponse(BaseModel):
    success: bool
    result: Any = None
    error: str | None = None


class HarnessPromptRequest(BaseModel):
    prompt: str


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/mcp/servers", response_model=list[MCPServerInfo])
async def list_mcp_servers() -> list[MCPServerInfo]:
    """Return every configured MCP server with its available tools.

    The server list is loaded from ``config/mcp_registry.yaml`` and tools
    are taken from the pre-connected harness results.
    """
    registry = load_mcp_registry()
    result: list[MCPServerInfo] = []

    for name, entry in registry.servers.items():
        result.append(
            MCPServerInfo(
                name=name,
                prompt=entry.get("prompt"),
                transport=entry.get("transport", ""),
                url=entry.get("url", ""),
                tools=_mcp_tools.get(name, []),
            )
        )

    return result


@router.post("/mcp/call", response_model=MCPCallResponse)
async def call_mcp_tool(req: MCPCallRequest) -> MCPCallResponse:
    """Invoke a specific tool on a connected MCP server."""
    if req.server_name not in _mcp_clients:
        available = sorted(_mcp_clients)
        raise HTTPException(
            status_code=404,
            detail=f"Server '{req.server_name}' not found. Available: {available}",
        )

    tools = _mcp_clients[req.server_name]
    tool = next((t for t in tools if getattr(t, "name", "") == req.tool_name), None)

    if tool is None:
        available = [getattr(t, "name", "") for t in tools]
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{req.tool_name}' not found on '{req.server_name}'. "
            f"Available: {available}",
        )

    try:
        result = await tool.ainvoke(req.arguments)
        # Serialize to JSON-friendly form
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        elif hasattr(result, "dict"):
            result = result.dict()
        return MCPCallResponse(success=True, result=result)
    except Exception as exc:
        logger.exception("MCP tool call failed: %s", exc)
        return MCPCallResponse(success=False, error=str(exc))


@router.post("/harness/prompt")
async def harness_prompt(req: HarnessPromptRequest) -> dict[str, Any]:
    """**Not yet implemented.**  Placeholder for AI Harness orchestration."""
    raise HTTPException(
        status_code=501,
        detail="AI Harness prompt endpoint is not yet implemented.",
    )
