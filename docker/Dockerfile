# =============================================================================
# ai-action-harness — multi-stage build (Vue frontend + Python backend)
# =============================================================================

# ── Stage 1: Build Vue frontend ───────────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package installer, matches the project's uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Working directory
WORKDIR /app

# Install Python dependencies (layer cached until pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Copy built Vue frontend from Stage 1
# Vite outputs to ../src/static relative to frontend/ → /src/static in the builder
COPY --from=frontend-builder /src/static/ ./src/static/

# Default command — run harness startup checks then the web server
CMD ["uv", "run", "src/server.py"]
