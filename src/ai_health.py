"""
AI Platform Health Checks
=========================

Parallel boot-time connectivity verification for every configured AI
platform.  Two checks run per platform:

1. **Zero-token auth check** — list available models via the provider's
   REST API to confirm network connectivity, base URL, and API key
   validity without consuming any generation tokens.
2. **1-token inference test** — send a minimal prompt with
   ``max_tokens=1`` to verify the actual generation pipeline works
   end-to-end.

All platform checks execute concurrently via ``asyncio.to_thread``.
Results are collected silently and then reported in a single summary
block.  If **any** platform check fails the harness terminates after
output.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from google.genai import types as genai_types

from src.models import ModelRegistry, PlatformConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PlatformHealthResult:
    """Outcome of the two checks for a single AI platform."""

    platform_name: str
    model_list_success: bool = False
    model_list_count: int = 0
    model_list_error: str | None = None
    inference_success: bool = False
    inference_error: str | None = None
    model_names: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.model_list_success and self.inference_success


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_ai_health_checks(registry: ModelRegistry) -> bool:
    """Execute platform health checks **in parallel** and report results.

    Parameters
    ----------
    registry:
        The sealed model registry loaded from ``config/models.yaml``.

    Returns
    -------
    bool
        ``True`` if every platform passed both checks, ``False`` otherwise.
        The caller should terminate the harness on ``False``.
    """
    if not registry.models:
        logger.info("No AI models configured — skipping health checks.")
        return True

    # Derive unique platforms from model configs, picking one
    # representative model per platform for the 1-token inference test.
    unique_platforms: dict[str, tuple[PlatformConfig, str]] = {}
    for model_cfg in registry.models.values():
        platform_name = model_cfg.platform.name
        if platform_name not in unique_platforms:
            unique_platforms[platform_name] = (
                model_cfg.platform,
                model_cfg.base_model,
            )

    # ── Launch every platform check concurrently ────────────────────────
    tasks: dict[str, asyncio.Task[PlatformHealthResult]] = {}
    for name, (platform_cfg, inference_model) in unique_platforms.items():
        tasks[name] = asyncio.create_task(
            _check_platform(platform_cfg, inference_model),
            name=f"health-{name}",
        )

    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results: dict[str, PlatformHealthResult] = {}
    for (name, task), outcome in zip(tasks.items(), gathered):
        if isinstance(outcome, BaseException):
            results[name] = PlatformHealthResult(
                platform_name=name,
                model_list_error=f"Internal error: {outcome}",
                inference_error=f"Internal error: {outcome}",
            )
        else:
            results[name] = outcome

    # ── Report ──────────────────────────────────────────────────────────
    _report_results(results)
    return all(r.healthy for r in results.values())


# ---------------------------------------------------------------------------
# Per-platform check (runs in a thread)
# ---------------------------------------------------------------------------


async def _check_platform(
    platform_cfg: PlatformConfig,
    inference_model: str,
) -> PlatformHealthResult:
    """Run both checks for *platform_cfg* inside a worker thread.

    The SDKs (``openai`` and ``google-genai``) are synchronous, so we
    offload the work to ``asyncio.to_thread`` to keep the event loop
    free while other platform checks run in parallel.
    """
    return await asyncio.to_thread(_check_platform_sync, platform_cfg, inference_model)


def _check_platform_sync(
    platform_cfg: PlatformConfig,
    inference_model: str,
) -> PlatformHealthResult:
    """Synchronous body of the platform health check."""
    result = PlatformHealthResult(platform_name=platform_cfg.name)

    if platform_cfg.name == "DeepSeek":
        _check_deepseek(platform_cfg, inference_model, result)
    elif platform_cfg.name == "Gemini":
        _check_gemini(platform_cfg, inference_model, result)
    else:
        result.model_list_error = f"Unknown platform type: {platform_cfg.name}"
        result.inference_error = f"Unknown platform type: {platform_cfg.name}"

    return result


# ---------------------------------------------------------------------------
# DeepSeek (OpenAI-compatible)
# ---------------------------------------------------------------------------


def _check_deepseek(
    platform_cfg: PlatformConfig,
    inference_model: str,
    result: PlatformHealthResult,
) -> None:
    client = platform_cfg.client

    # ── 1. Model listing ────────────────────────────────────────────────
    try:
        models = client.models.list()
        result.model_list_success = True
        result.model_list_count = len(models.data)
        result.model_names = [m.id for m in models.data]
    except Exception as exc:
        result.model_list_error = str(exc)

    # ── 2. 1-token inference ────────────────────────────────────────────
    try:
        client.chat.completions.create(
            model=inference_model,
            messages=[{"role": "user", "content": "Ping."}],
            max_tokens=1,
        )
        result.inference_success = True
    except Exception as exc:
        result.inference_error = str(exc)


# ---------------------------------------------------------------------------
# Gemini (Google GenAI)
# ---------------------------------------------------------------------------


def _check_gemini(
    platform_cfg: PlatformConfig,
    inference_model: str,
    result: PlatformHealthResult,
) -> None:
    client = platform_cfg.client

    # ── 1. Model listing ────────────────────────────────────────────────
    try:
        models = list(client.models.list())
        result.model_list_success = True
        result.model_list_count = len(models)
        result.model_names = [m.name for m in models]
    except Exception as exc:
        result.model_list_error = str(exc)

    # ── 2. 1-token inference ────────────────────────────────────────────
    try:
        client.models.generate_content(
            model=inference_model,
            contents="Ping.",
            config=genai_types.GenerateContentConfig(max_output_tokens=1),
        )
        result.inference_success = True
    except Exception as exc:
        result.inference_error = str(exc)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _report_results(results: dict[str, PlatformHealthResult]) -> None:
    """Log a human-readable summary of every platform's health."""
    separator = "─" * 60
    logger.info(separator)
    logger.info("AI Platform Health Check Results")
    logger.info(separator)

    for name in sorted(results):
        r = results[name]
        status = "✓ HEALTHY" if r.healthy else "✗ UNHEALTHY"
        logger.info("")

        # ── Model listing ────────────────────────────────────────────────
        if r.model_list_success:
            logger.info(
                "  [%s] %s — Model listing: %d model(s) available",
                name,
                status,
                r.model_list_count,
            )
            # Print all model names in reverse alphabetical order.
            for m_name in sorted(r.model_names):
                logger.info("    • %s", m_name)
        else:
            logger.error(
                "  [%s] %s — Model listing FAILED: %s",
                name,
                status,
                r.model_list_error,
            )

        # ── 1-token inference ────────────────────────────────────────────
        if r.inference_success:
            logger.info(
                "  [%s] %s — 1-token inference: SUCCESS",
                name,
                status,
            )
        else:
            logger.error(
                "  [%s] %s — 1-token inference FAILED: %s",
                name,
                status,
                r.inference_error,
            )

    logger.info("")
    logger.info(separator)

    healthy_count = sum(1 for r in results.values() if r.healthy)
    total = len(results)
    logger.info("AI health summary: %d/%d platform(s) healthy.", healthy_count, total)
    logger.info(separator)
