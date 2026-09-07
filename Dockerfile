# Multi-stage Dockerfile for tancat-ai/tancat (product image).
#
# Fixed 2026-08-15 (latent flaws documented in the Phase 7a BACKLOG entry,
# all three proven in Dockerfile.action):
#   1. EMPTY-PROJECT-WHEEL FLAW — the old single `uv sync` ran BEFORE `COPY . .`,
#      so the project wheel (hatchling: packages = ["src", "cli"]) built from a
#      context with no src/ or cli/. The venv carried an empty project install
#      and imports of the tool's own modules failed at runtime. Fix: two-stage
#      sync — `--no-install-project` first (deps only, warm cache), full sync
#      after the repo is copied.
#   2. `~/.cargo/bin/uv` PATH — the uv installer's default dir varies by shell
#      profile and moved across releases, so the old path broke on newer
#      installer versions. Fix: explicit UV_INSTALL_DIR=/usr/local/bin.
#   3. PYTHON VERSION MISMATCH — the old runtime base
#      (mcr.microsoft.com/playwright/python:v1.50.0-jammy) ships python 3.10,
#      while the repo requires >= 3.14 (PEP 758 exception syntax;
#      requires-python in pyproject). A 3.14-built venv on that base silently
#      failed. Fix: python:3.14-slim runtime, with browsers installed from the
#      venv's OWN playwright (uv.lock) so the browser version always matches
#      the driver — never the image's stale 1.50 bundle.
#
# Build context is the repository root:
#     docker build -t ai-test-generator .

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

# Copy the rest of the repo (src/, cli/, scripts/, ...) so the project
# wheel builds with real content. Deps are already installed above and uv's
# wheel cache is warm, so this second sync is incremental.
COPY . .
RUN uv sync --frozen --no-dev --python /usr/local/bin/python3

# Runtime stage: python 3.14 (matches the venv; the repo requires >= 3.14 —
# the old playwright/python:v1.50.0-jammy base shipped python 3.10)
FROM python:3.14-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Chromium + system deps, from the venv's own playwright (version-matched).
# Explicit /app/.venv/bin/python — do not rely on PATH resolution inside RUN.
RUN /app/.venv/bin/python -m playwright install --with-deps chromium

# Copy application code
COPY . .

# Default command: Run Streamlit app
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
