# syntax=docker/dockerfile:1
#
# Multi-stage build for the Astrocyte API service.
# Build context is the repository root: `docker build -f docker/Dockerfile .`
# Base image is Debian 12 (bookworm) slim, per ADR-001.

# ---- Builder: resolve and install dependencies with uv --------------------
FROM python:3.14-slim-bookworm AS builder

# Pinned uv binary (kept current by Dependabot's docker ecosystem).
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install third-party deps first as a cacheable layer (no project sources yet).
# The RV subsystems ship in the image (ADR-010): rvc (bridge), ha + mcp (HA
# MCP server), agents (CoachAgent). rag stays out until phase 2.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev \
    --extra rvc --extra ha --extra mcp --extra agents

# Then add the project sources and install the package itself.
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    --extra rvc --extra ha --extra mcp --extra agents

# ---- Runtime: minimal image with just the venv ----------------------------
FROM python:3.14-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 astrocyte
WORKDIR /app

COPY --from=builder --chown=astrocyte:astrocyte /app/.venv /app/.venv
COPY --from=builder --chown=astrocyte:astrocyte /app/src /app/src

# Writable state dir for the API (approvals.db, audit.jsonl). Create it owned by
# astrocyte so a fresh named volume mounted here inherits uid 1000 ownership —
# otherwise Docker creates the volume root-owned and the non-root process can't
# open the sqlite db.
RUN mkdir -p /app/state && chown astrocyte:astrocyte /app/state

ENV PATH="/app/.venv/bin:$PATH"
USER astrocyte
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"]

CMD ["uvicorn", "astrocyte.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
