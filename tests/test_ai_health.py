"""Tests for the AI platform health-check module."""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

from src.ai_health import (
    PlatformHealthResult,
    _check_deepseek,
    _check_gemini,
    _check_platform_sync,
    _report_results,
    run_ai_health_checks,
)
from src.models import (
    ModelConfig,
    ModelRegistry,
    PlatformConfig,
)

# ---------------------------------------------------------------------------
# PlatformHealthResult
# ---------------------------------------------------------------------------


class TestPlatformHealthResult:
    def test_healthy_when_both_pass(self):
        r = PlatformHealthResult(
            platform_name="X",
            model_list_success=True,
            inference_success=True,
        )
        assert r.healthy is True

    def test_unhealthy_when_list_fails(self):
        r = PlatformHealthResult(
            platform_name="X",
            model_list_success=False,
            inference_success=True,
        )
        assert r.healthy is False

    def test_unhealthy_when_inference_fails(self):
        r = PlatformHealthResult(
            platform_name="X",
            model_list_success=True,
            inference_success=False,
        )
        assert r.healthy is False

    def test_unhealthy_when_both_fail(self):
        r = PlatformHealthResult(
            platform_name="X",
            model_list_success=False,
            inference_success=False,
        )
        assert r.healthy is False


# ---------------------------------------------------------------------------
# DeepSeek checks
# ---------------------------------------------------------------------------


class TestDeepSeekChecks:
    def test_both_succeed(self):
        cfg = PlatformConfig(name="DeepSeek", url="https://api.ds", api_key="k")
        result = PlatformHealthResult(platform_name="DeepSeek")

        with mock.patch("src.models.OpenAI") as MockOpenAI:
            mock_client = MockOpenAI.return_value

            mock_list = mock.MagicMock()
            mock_list.data = [
                mock.MagicMock(id="deepseek-chat"),
                mock.MagicMock(id="deepseek-reasoner"),
            ]
            mock_client.models.list.return_value = mock_list
            mock_client.chat.completions.create.return_value = mock.MagicMock()

            _check_deepseek(cfg, "deepseek-chat", result)

        assert result.model_list_success is True
        assert result.model_list_count == 2
        assert result.model_names == ["deepseek-chat", "deepseek-reasoner"]
        assert result.inference_success is True

    def test_list_fails_inference_succeeds(self):
        cfg = PlatformConfig(name="DeepSeek", url="https://api.ds", api_key="k")
        result = PlatformHealthResult(platform_name="DeepSeek")

        with mock.patch("src.models.OpenAI") as MockOpenAI:
            mock_client = MockOpenAI.return_value
            mock_client.models.list.side_effect = RuntimeError("auth failed")
            mock_client.chat.completions.create.return_value = mock.MagicMock()

            _check_deepseek(cfg, "deepseek-chat", result)

        assert result.model_list_success is False
        assert "auth failed" in result.model_list_error
        assert result.inference_success is True

    def test_inference_fails(self):
        cfg = PlatformConfig(name="DeepSeek", url="https://api.ds", api_key="k")
        result = PlatformHealthResult(platform_name="DeepSeek")

        with mock.patch("src.models.OpenAI") as MockOpenAI:
            mock_client = MockOpenAI.return_value
            mock_list = mock.MagicMock()
            mock_list.data = []
            mock_client.models.list.return_value = mock_list
            mock_client.chat.completions.create.side_effect = RuntimeError(
                "model not found"
            )

            _check_deepseek(cfg, "bad-model", result)

        assert result.model_list_success is True
        assert result.inference_success is False
        assert "model not found" in result.inference_error


# ---------------------------------------------------------------------------
# Gemini checks
# ---------------------------------------------------------------------------


class TestGeminiChecks:
    def test_both_succeed(self):
        cfg = PlatformConfig(
            name="Gemini",
            url="https://generativelanguage.googleapis.com/v1beta",
            api_key="k",
        )
        result = PlatformHealthResult(platform_name="Gemini")

        with mock.patch("src.models.genai.Client") as MockClient:
            mock_client = MockClient.return_value

            mock_model_a = mock.MagicMock()
            mock_model_a.name = "models/gemini-2.0-flash"
            mock_model_b = mock.MagicMock()
            mock_model_b.name = "models/gemini-2.0-pro"
            mock_client.models.list.return_value = [mock_model_a, mock_model_b]

            _check_gemini(cfg, "gemini-2.0-flash", result)

        assert result.model_list_success is True
        assert result.model_list_count == 2
        assert result.model_names == [
            "models/gemini-2.0-flash",
            "models/gemini-2.0-pro",
        ]
        assert result.inference_success is True

    def test_list_fails_inference_succeeds(self):
        cfg = PlatformConfig(
            name="Gemini",
            url="https://generativelanguage.googleapis.com/v1beta",
            api_key="k",
        )
        result = PlatformHealthResult(platform_name="Gemini")

        with mock.patch("src.models.genai.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_client.models.list.side_effect = RuntimeError("unauthorized")

            _check_gemini(cfg, "gemini-2.0-flash", result)

        assert result.model_list_success is False
        assert "unauthorized" in result.model_list_error
        assert result.inference_success is True

    def test_inference_fails(self):
        cfg = PlatformConfig(
            name="Gemini",
            url="https://generativelanguage.googleapis.com/v1beta",
            api_key="k",
        )
        result = PlatformHealthResult(platform_name="Gemini")

        with mock.patch("src.models.genai.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_client.models.list.return_value = []
            mock_client.models.generate_content.side_effect = RuntimeError(
                "quota exceeded"
            )

            _check_gemini(cfg, "bad-model", result)

        assert result.model_list_success is True
        assert result.inference_success is False
        assert "quota exceeded" in result.inference_error


# ---------------------------------------------------------------------------
# _check_platform_sync dispatch
# ---------------------------------------------------------------------------


class TestCheckPlatformSync:
    def test_dispatches_to_deepseek(self):
        cfg = PlatformConfig(name="DeepSeek", url="https://api.ds", api_key="k")
        with mock.patch("src.ai_health._check_deepseek") as mock_check:
            _check_platform_sync(cfg, "deepseek-chat")
            mock_check.assert_called_once()

    def test_dispatches_to_gemini(self):
        cfg = PlatformConfig(name="Gemini", url="https://g", api_key="k")
        with mock.patch("src.ai_health._check_gemini") as mock_check:
            _check_platform_sync(cfg, "gemini-flash")
            mock_check.assert_called_once()

    def test_unknown_platform(self):
        cfg = PlatformConfig(name="UnknownAI", url="https://x", api_key="k")
        result = _check_platform_sync(cfg, "m")
        assert result.healthy is False
        assert "Unknown platform" in result.model_list_error
        assert "Unknown platform" in result.inference_error


# ---------------------------------------------------------------------------
# run_ai_health_checks integration
# ---------------------------------------------------------------------------


class TestRunAiHealthChecks:
    @mock.patch("src.ai_health._check_platform_sync")
    @pytest.mark.asyncio
    async def test_all_healthy_returns_true(self, mock_sync):
        mock_sync.return_value = PlatformHealthResult(
            platform_name="DeepSeek",
            model_list_success=True,
            inference_success=True,
            model_list_count=5,
            model_names=["m1", "m2"],
        )

        reg = ModelRegistry(
            models={
                "coder": ModelConfig(
                    name="coder",
                    platform=PlatformConfig(
                        name="DeepSeek", url="https://api.ds", api_key="k"
                    ),
                    base_model="deepseek-v4-pro",
                    temperature=0.7,
                    max_tokens=4000,
                ),
            },
        )

        healthy = await run_ai_health_checks(reg)
        assert healthy is True

    @mock.patch("src.ai_health._check_platform_sync")
    @pytest.mark.asyncio
    async def test_any_unhealthy_returns_false(self, mock_sync):
        mock_sync.return_value = PlatformHealthResult(
            platform_name="DeepSeek",
            model_list_success=False,
            inference_success=False,
            model_list_error="bad auth",
            inference_error="bad auth",
        )

        reg = ModelRegistry(
            models={
                "coder": ModelConfig(
                    name="coder",
                    platform=PlatformConfig(
                        name="DeepSeek", url="https://api.ds", api_key="k"
                    ),
                    base_model="deepseek-v4-pro",
                    temperature=0.7,
                    max_tokens=4000,
                ),
            },
        )

        healthy = await run_ai_health_checks(reg)
        assert healthy is False

    @pytest.mark.asyncio
    async def test_no_platforms_skips_and_returns_true(self):
        reg = ModelRegistry()
        healthy = await run_ai_health_checks(reg)
        assert healthy is True

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Both platforms execute concurrently (not sequentially)."""
        call_order: list[str] = []

        async def _slow_check(cfg, model):
            await asyncio.sleep(0.05)
            call_order.append(cfg.name)
            return PlatformHealthResult(
                platform_name=cfg.name,
                model_list_success=True,
                inference_success=True,
            )

        reg = ModelRegistry(
            models={
                "coder": ModelConfig(
                    name="coder",
                    platform=PlatformConfig(
                        name="DeepSeek", url="https://api.ds", api_key="k"
                    ),
                    base_model="deepseek-v4-pro",
                    temperature=0.7,
                    max_tokens=4000,
                ),
                "analysis": ModelConfig(
                    name="analysis",
                    platform=PlatformConfig(
                        name="Gemini", url="https://g", api_key="k2"
                    ),
                    base_model="gemini-pro",
                    temperature=0.8,
                    max_tokens=8000,
                ),
            },
        )

        with mock.patch("src.ai_health._check_platform", side_effect=_slow_check):
            await run_ai_health_checks(reg)

        assert sorted(call_order) == ["DeepSeek", "Gemini"]


# ---------------------------------------------------------------------------
# _report_results (log capture)
# ---------------------------------------------------------------------------


class TestReportResults:
    def test_reports_healthy_and_unhealthy(self, caplog):
        import logging

        caplog.set_level(logging.INFO)

        results = {
            "DeepSeek": PlatformHealthResult(
                platform_name="DeepSeek",
                model_list_success=True,
                model_list_count=3,
                model_names=["a", "b", "c"],
                inference_success=True,
            ),
            "Gemini": PlatformHealthResult(
                platform_name="Gemini",
                model_list_success=False,
                model_list_error="Connection refused",
                inference_success=False,
                inference_error="Connection refused",
            ),
        }

        _report_results(results)

        text = caplog.text
        assert "HEALTHY" in text
        assert "UNHEALTHY" in text
        assert "1/2 platform(s) healthy" in text
        assert "Connection refused" in text
