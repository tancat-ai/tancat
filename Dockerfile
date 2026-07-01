
# Multi-stage Dockerfile for AI-Playwright-Test-Generator

# Builder stage: Install dependencies using uv
FROM python:3.14-slim AS builder

WORKDIR /app

# Install system dependencies for uv and Playwright
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy uv files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv (frozen mode for reproducibility)
RUN ~/.cargo/bin/uv sync --frozen --no-dev

# Runtime stage: Use Playwright's official Python image (includes system dependencies for browsers)
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy AS runtime

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default command: Run Streamlit app
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
