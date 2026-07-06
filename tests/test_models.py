"""Tests for the AI model registry module."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import mock

import pytest
import yaml

from src.models import (
    ModelConfig,
    ModelRegistry,
    PlatformConfig,
    load_model_registry,
)

# ---------------------------------------------------------------------------
# Sample YAML
# ---------------------------------------------------------------------------

SAMPLE_YAML = {
    "ai": {
        "platforms": {
            "DeepSeek": {
                "url": "https://api.deepseek.com/v1",
                "apiKey": "TEST_DEEPSEEK_KEY",
            },
            "Gemini": {
                "url": "https://generativelanguage.googleapis.com/v1beta",
                "apiKey": "TEST_GEMINI_KEY",
            },
        },
        "models": {
            "coder-deepseek-v4-pro": {
                "platform": "DeepSeek",
                "base_model": "deepseek-v4-pro",
                "temperature": 0.7,
                "max_tokens": 4000,
            },
            "gemini-analysis": {
                "platform": "Gemini",
                "base_model": "gemini-v3.1-pro-preview",
                "temperature": 0.8,
                "max_tokens": 8000,
            },
        },
        "roles": {
            "Architect": "coder-deepseek-v4-pro",
        },
    }
}


def _write_temp_yaml(data: dict) -> Path:
    """Write *data* to a temporary YAML file and return its path."""
    tmp = NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.safe_dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# PlatformConfig
# ---------------------------------------------------------------------------


class TestPlatformConfig:
    def test_frozen(self):
        cfg = PlatformConfig(name="X", url="http://x", api_key="k")
        with pytest.raises(Exception):
            cfg.name = "Y"  # type: ignore[misc]

    def test_fields(self):
        cfg = PlatformConfig(name="Gemini", url="https://g", api_key="abc")
        assert cfg.name == "Gemini"
        assert cfg.url == "https://g"
        assert cfg.api_key == "abc"


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_frozen(self):
        cfg = ModelConfig(
            name="m",
            platform=PlatformConfig(name="p", url="http://u", api_key="k"),
            base_model="b",
            temperature=0.5,
            max_tokens=100,
        )
        with pytest.raises(Exception):
            cfg.temperature = 1.0  # type: ignore[misc]

    def test_fields(self):
        cfg = ModelConfig(
            name="coder",
            platform=PlatformConfig(
                name="DeepSeek", url="https://api.deepseek.com/v1", api_key="sk-123"
            ),
            base_model="deepseek-v4-pro",
            temperature=0.7,
            max_tokens=4000,
        )
        assert cfg.name == "coder"
        assert cfg.base_model == "deepseek-v4-pro"
        assert cfg.temperature == 0.7


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    def test_get_model_success(self):
        reg = ModelRegistry(
            models={
                "m": ModelConfig(
                    name="m",
                    platform=PlatformConfig(name="p", url="u", api_key="k"),
                    base_model="b",
                    temperature=0.5,
                    max_tokens=100,
                )
            },
        )
        assert reg.get_model("m").name == "m"

    def test_get_model_missing_raises(self):
        reg = ModelRegistry()
        with pytest.raises(KeyError, match="Unknown model"):
            reg.get_model("nope")

    def test_resolve_role_success(self):
        reg = ModelRegistry(
            models={
                "m": ModelConfig(
                    name="m",
                    platform=PlatformConfig(name="p", url="u", api_key="k"),
                    base_model="b",
                    temperature=0.5,
                    max_tokens=100,
                )
            },
            roles={"Architect": "m"},
        )
        assert reg.resolve_role("Architect").name == "m"

    def test_resolve_role_missing_raises(self):
        reg = ModelRegistry()
        with pytest.raises(KeyError, match="Unknown role"):
            reg.resolve_role("Nope")

    def test_resolve_role_bad_model_raises(self):
        reg = ModelRegistry(roles={"Architect": "ghost"})
        with pytest.raises(KeyError, match="Unknown model"):
            reg.resolve_role("Architect")


# ---------------------------------------------------------------------------
# load_model_registry
# ---------------------------------------------------------------------------


class TestLoadModelRegistry:
    @mock.patch.dict(
        os.environ,
        {
            "TEST_DEEPSEEK_KEY": "dk-key",
            "TEST_GEMINI_KEY": "gm-key",
        },
    )
    def test_loads_platforms_and_models(self):
        path = _write_temp_yaml(SAMPLE_YAML)
        try:
            reg = load_model_registry(path)
            assert len(reg.models) == 2
            assert len(reg.roles) == 1
            # Verify platform configs are accessible through models.
            assert reg.get_model("coder-deepseek-v4-pro").platform.api_key == "dk-key"
            assert reg.get_model("gemini-analysis").platform.api_key == "gm-key"
        finally:
            path.unlink()

    @mock.patch.dict(
        os.environ,
        {
            "TEST_DEEPSEEK_KEY": "dk-key",
            "TEST_GEMINI_KEY": "gm-key",
        },
    )
    def test_model_config_is_complete(self):
        path = _write_temp_yaml(SAMPLE_YAML)
        try:
            reg = load_model_registry(path)
            m = reg.get_model("coder-deepseek-v4-pro")
            assert m.platform.name == "DeepSeek"
            assert m.base_model == "deepseek-v4-pro"
            assert m.temperature == 0.7
            assert m.max_tokens == 4000
            assert m.platform.api_key == "dk-key"
            assert m.platform.url == "https://api.deepseek.com/v1"
        finally:
            path.unlink()

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_env_var_raises(self):
        path = _write_temp_yaml(SAMPLE_YAML)
        try:
            with pytest.raises(RuntimeError, match="TEST_DEEPSEEK_KEY"):
                load_model_registry(path)
        finally:
            path.unlink()

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_model_registry("nonexistent.yaml")

    @mock.patch.dict(
        os.environ,
        {
            "TEST_DEEPSEEK_KEY": "dk-key",
            "TEST_GEMINI_KEY": "gm-key",
        },
    )
    def test_bad_platform_ref_raises(self):
        bad = copy.deepcopy(SAMPLE_YAML)
        bad["ai"]["models"]["coder-deepseek-v4-pro"]["platform"] = "Unknown"
        path = _write_temp_yaml(bad)
        try:
            with pytest.raises(ValueError, match="unknown platform"):
                load_model_registry(path)
        finally:
            path.unlink()

    @mock.patch.dict(
        os.environ,
        {
            "TEST_DEEPSEEK_KEY": "dk-key",
            "TEST_GEMINI_KEY": "gm-key",
        },
    )
    def test_bad_role_ref_raises(self):
        bad = copy.deepcopy(SAMPLE_YAML)
        bad["ai"]["roles"]["Ghost"] = "nonexistent-model"
        path = _write_temp_yaml(bad)
        try:
            with pytest.raises(ValueError, match="Ghost"):
                load_model_registry(path)
        finally:
            path.unlink()

    def test_registry_is_hashable_for_caching(self):
        """The registry itself isn't hashable (contains dicts), but
        individual frozen configs should be."""
        cfg = ModelConfig(
            name="m",
            platform=PlatformConfig(name="p", url="u", api_key="k"),
            base_model="b",
            temperature=0.5,
            max_tokens=100,
        )
        # Frozen dataclasses are hashable if all fields are hashable.
        assert hash(cfg) is not None
