"""
AI Model Registry
=================

Parses ``config/models.yaml`` at import time, resolves API keys from
environment variables, and produces sealed (frozen) dataclass instances
for every configured platform and model.

These objects are intended to be created once at startup and never
mutated — a harness reboot is required to pick up configuration changes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/models.yaml")


# ---------------------------------------------------------------------------
# Sealed configuration objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlatformConfig:
    """Immutable platform-level configuration with a resolved API key."""

    name: str
    url: str
    api_key: str
    """Resolved API key value (not the env-var name)."""

    @cached_property
    def client(self) -> Any:
        """Lazily-created API client for this platform.

        The client is cached on first access — subsequent calls return the
        same instance, avoiding repeated connection overhead.
        """
        if self.name == "DeepSeek":
            return OpenAI(base_url=self.url, api_key=self.api_key)
        if self.name == "Gemini":
            return genai.Client(api_key=self.api_key)
        raise ValueError(f"Unsupported platform: {self.name}")


@dataclass(frozen=True)
class ModelConfig:
    """Immutable model-level configuration bundling everything needed to call
    the remote AI service.

    All fields flow from the YAML definition and the resolved platform.
    """

    name: str
    """Custom alias used within the harness (e.g. ``coder-deepseek-v4-pro``)."""

    platform: PlatformConfig
    """The resolved platform this model runs on."""

    base_model: str
    """The upstream model identifier (e.g. ``deepseek-v4-pro``)."""

    temperature: float
    max_tokens: int


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRegistry:
    """Immutable snapshot of the full model configuration.

    Created once at module-load time via :func:`load_model_registry`.
    """

    models: dict[str, ModelConfig] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)

    def get_model(self, name: str) -> ModelConfig:
        """Look up a model by its harness alias."""
        if name not in self.models:
            available = sorted(self.models)
            raise KeyError(f"Unknown model '{name}'. Available: {available}")
        return self.models[name]

    def resolve_role(self, role: str) -> ModelConfig:
        """Resolve a role name (e.g. ``Architect``) to its :class:`ModelConfig`."""
        if role not in self.roles:
            available = sorted(self.roles)
            raise KeyError(f"Unknown role '{role}'. Available: {available}")
        model_name = self.roles[role]
        return self.get_model(model_name)

    def create_client(self, model: ModelConfig) -> Any:
        """Return an API client configured for *model*'s platform.

        Returns
        -------
        openai.OpenAI | google.genai.Client
            The appropriate client for the platform.
        """
        return model.platform.client

    def generate(
        self,
        model_name: str,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        """Convenience method: generate a completion from a model alias.

        Parameters
        ----------
        model_name:
            Harness model alias (e.g. ``coder-deepseek-v4-pro``).
        prompt:
            The user message content.
        system_prompt:
            Optional system-level instruction.
        """
        model = self.get_model(model_name)
        client = model.platform.client

        if model.platform.name == "DeepSeek":
            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model.base_model,
                messages=messages,
                temperature=model.temperature,
                max_tokens=model.max_tokens,
            )
            return response.choices[0].message.content or ""

        if model.platform.name == "Gemini":
            contents = prompt
            if system_prompt:
                contents = f"{system_prompt}\n\n{prompt}"

            response = client.models.generate_content(
                model=model.base_model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    temperature=model.temperature,
                    max_output_tokens=model.max_tokens,
                ),
            )
            return response.text or ""

        raise ValueError(f"Unsupported platform: {model.platform.name}")


# ---------------------------------------------------------------------------
# YAML loading & API-key resolution
# ---------------------------------------------------------------------------


def _resolve_api_key(env_var_name: str) -> str:
    """Read an API key from the environment, with diagnostics on failure."""
    key = os.environ.get(env_var_name)
    if key:
        logger.debug("Resolved API key from env var '%s'.", env_var_name)
        return key

    # ── nothing found — emit diagnostics ────────────────────────────────
    api_env_vars = sorted(
        k for k in os.environ if "API" in k.upper() or "KEY" in k.upper()
    )
    if api_env_vars:
        logger.warning(
            "API key resolution failed for '%s'. Relevant env vars present: %s",
            env_var_name,
            ", ".join(api_env_vars),
        )
    else:
        logger.warning(
            "API key resolution failed for '%s'. "
            "No API-related environment variables found in the container.",
            env_var_name,
        )

    raise RuntimeError(
        f"Environment variable '{env_var_name}' is not set. "
        f"Set it on your host system (e.g. 'setx {env_var_name} sk-...' "
        f"or '$env:{env_var_name} = \"sk-...\"' in PowerShell), "
        f"then restart your terminal and run 'docker compose up' again."
    )


def load_model_registry(config_path: str | Path = CONFIG_PATH) -> ModelRegistry:
    """Parse *config_path*, resolve API keys, and return a frozen registry.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    RuntimeError
        If any referenced environment variable is missing.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Model configuration not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    ai_section = raw.get("ai", {})
    platforms_raw: dict[str, dict[str, str]] = ai_section.get("platforms", {})
    models_raw: dict[str, dict[str, Any]] = ai_section.get("models", {})
    roles_raw: dict[str, str] = ai_section.get("roles", {})

    # ── Resolve platforms ───────────────────────────────────────────────
    platforms: dict[str, PlatformConfig] = {}
    for name, cfg in platforms_raw.items():
        api_key = _resolve_api_key(cfg["apiKey"])
        platforms[name] = PlatformConfig(
            name=name,
            url=cfg["url"],
            api_key=api_key,
        )

    # ── Resolve models ──────────────────────────────────────────────────
    models: dict[str, ModelConfig] = {}
    for alias, cfg in models_raw.items():
        platform_name = cfg.get("platform", "")
        if platform_name not in platforms:
            available = sorted(platforms)
            raise ValueError(
                f"Model '{alias}' references unknown platform "
                f"'{platform_name}'. Available: {available}"
            )

        platform_cfg = platforms[platform_name]
        models[alias] = ModelConfig(
            name=alias,
            platform=platform_cfg,
            base_model=cfg["base_model"],
            temperature=float(cfg.get("temperature", 0.7)),
            max_tokens=int(cfg.get("max_tokens", 4000)),
        )

    # ── Validate role → model references ────────────────────────────────
    for role_name, model_alias in roles_raw.items():
        if model_alias not in models:
            available = sorted(models)
            raise ValueError(
                f"Role '{role_name}' references unknown model "
                f"'{model_alias}'. Available: {available}"
            )

    logger.info(
        "Loaded %d platform(s), %d model(s), %d role(s).",
        len(platforms),
        len(models),
        len(roles_raw),
    )

    return ModelRegistry(
        models=models,
        roles=roles_raw,
    )
