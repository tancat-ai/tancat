# Dockerfile for the Phase 7 CI/CD GitHub Action image.
#
# Separate from the product Dockerfile on purpose: the product image's CMD
# runs Streamlit; the Action image is a headless entrypoint.
#
# Runtime base is python:3.14-slim (NOT the playwright/python image) because
# the repo targets python >= 3.14 (PEP 758 exception syntax, requires-python
# in pyproject) while the mcr playwright/python:v1.50.0-jammy image ships
# python 3.10 — a venv built on 3.14 silently runs on 3.10 there (the product
# image's latent flaw; see BACKLOG). Browsers are installed from the venv's
# OWN playwright (uv.lock -> 1.61.0), so browser version always matches the
# driver — deterministic, never the image's stale 1.50 bundle.
#
# Build context is the repository root (same as the product image):
#     docker build -f action/Dockerfile -t ai-test-generator-action .

# Builder stage: install dependencies using uv
FROM python:3.14-slim AS builder

WORKDIR /app

# Install system dependencies for uv
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install uv (explicit install dir so the path is deterministic — the
# installer default varies by shell profile and has moved over releases)
ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Use the base image's python 3.14 for the venv (pinned explicitly on both
# syncs below). Without this uv may download its own managed CPython and the
# venv's bin/python symlinks into /root/.local/share/uv/python/... — a path
# that does NOT exist in the runtime stage, making the copied venv
# unexecutable there.
ENV UV_PYTHON_PREFERENCE=only-system

# Copy uv files first for better caching (README needed by the hatchling
# build backend — pyproject declares readme = "README.md")
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using uv (frozen mode for reproducibility). The
# project itself is skipped here: its wheel builds from src/ (hatchling
# packages = ["src", "cli"]), which is copied in the next layer — building
# it now would ship an EMPTY project install (no src importable).
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3

# Copy the rest of the repo (src/, scripts/, action/, ...) so the project
# wheel builds with real content. Deps are already installed above and uv's
# wheel cache is warm, so this second sync is incremental.
COPY . .
RUN uv sync --frozen --no-dev --python /usr/local/bin/python3

# Runtime stage: python 3.14 (matches the venv; the repo requires >= 3.14)
FROM python:3.14-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code (scripts/, src/, action/, generated_tests/conftest.py,
# mock_sites/ for hermetic self-tests, fixtures/)
COPY . .

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Chromium + system deps, from the venv's own playwright (version-matched).
# Explicit /app/.venv/bin/python — do not rely on PATH resolution inside RUN.
RUN /app/.venv/bin/python -m playwright install --with-deps chromium

# GitHub Actions Docker actions must have an entrypoint. The orchestrator
# (action/entrypoint.sh) is copied into the image root where action.yml points.
COPY action/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
