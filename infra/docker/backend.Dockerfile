# syntax=docker/dockerfile:1.7
# Tuitional Finance — backend (FastAPI + ledger engine).
#
# Multi-stage: build deps with uv, then a slim runtime that drops the
# build chain. Image runs as a non-root user.

FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY docs/chart_of_accounts.yaml ./docs/chart_of_accounts.yaml

RUN uv venv /opt/venv && uv sync --frozen --no-dev || uv sync --no-dev


# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    APP_PORT=3002

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 tuitional

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

USER tuitional

EXPOSE 3002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://127.0.0.1:3002/ || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "3002", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
