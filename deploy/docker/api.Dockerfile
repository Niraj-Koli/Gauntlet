# syntax=docker/dockerfile:1.7
# The Python backend: one image for the API (default command) and the trading floor
# (`python -m gauntlet.trading_floor`). Build from the repository root:
#   docker build -f deploy/docker/api.Dockerfile -t gauntlet-api .

ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
ARG NODE_IMAGE=node:24-trixie-slim@sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc

FROM ${UV_IMAGE} AS uv
FROM ${NODE_IMAGE} AS node

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# The researcher's MCP servers, installed at their pinned versions so runs never download
# anything. This layer only rebuilds when mcp_tools.py changes.
COPY apps/api/src/gauntlet/mcp_tools.py /tmp/mcp_tools.py
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.npm \
    python /tmp/mcp_tools.py /opt/mcp-tools

# Third-party dependencies first (cached until uv.lock changes), then the application.
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace
COPY apps/api/src apps/api/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable
# Packages' own test suites and the musl build of libsql (this image is glibc) are never used.
RUN find /app/.venv /opt/mcp-tools -type d -name tests -prune -exec rm -rf {} + \
 && rm -rf /opt/mcp-tools/node/node_modules/@libsql/linux-x64-musl

FROM ${PYTHON_IMAGE} AS runtime
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN useradd --uid 10001 --user-group --home-dir /home/gauntlet --create-home gauntlet \
 && mkdir /data \
 && chown gauntlet:gauntlet /data
COPY --from=build /opt/mcp-tools /opt/mcp-tools
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GAUNTLET_DATA_DIR=/data \
    MCP_TOOLS_DIR=/opt/mcp-tools \
    HEARTBEAT_FILE=/tmp/gauntlet-heartbeat \
    LITELLM_LOCAL_MODEL_COST_MAP=True
USER 10001
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
CMD ["uvicorn", "gauntlet.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
