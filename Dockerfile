# =============================================================================
# ai-action-harness — Python 3.12 container
# =============================================================================
FROM python:3.12-slim AS base

# ── System dependencies ──────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install uv (fast Python package installer, matches the project's uv.lock) ──
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ── Working directory ────────────────────────────────────────────────────
WORKDIR /app

# ── Install dependencies (layer is cached until pyproject.toml / uv.lock change) ──
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Copy source code and entry point ─────────────────────────────────────
COPY src/ ./src/
COPY config/ ./config/

# ── Default command ──────────────────────────────────────────────────────
CMD ["uv", "run", "src/harness.py"]
