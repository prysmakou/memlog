ARG BUILD_DIR=/build

# ── Stage 1: Frontend ─────────────────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend-build

ARG BUILD_DIR

RUN mkdir ${BUILD_DIR}
WORKDIR ${BUILD_DIR}

COPY package.json \
    package-lock.json \
    postcss.config.js \
    tailwind.config.js \
    vite.config.js \
    ./

RUN npm ci

COPY client ./client
RUN npm run build

# ── Stage 2: Python deps (backend + MCP server) ───────────────────────────────
FROM python:3.13-alpine AS python-deps

# gcc + musl-dev needed to compile some Python C extensions (e.g. cffi)
RUN apk add --no-cache gcc musl-dev

WORKDIR /build

COPY server/ ./server/
COPY mcp-server/ ./mcp-server/
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache ./server ./mcp-server && \
    uv pip install --system --no-cache "qdrant-client>=1.12"

# ── Stage 3: Runtime ──────────────────────────────────────────────────────────
FROM python:3.13-alpine

ARG BUILD_DIR

ENV PUID=1000
ENV PGID=1000
ENV EXEC_TOOL=su-exec
ENV MEMLOG_HOST=0.0.0.0
ENV MEMLOG_PORT=8080

ENV APP_PATH=/app
ENV MEMLOG_PATH=/data

# Whoosh uses invalid escape sequences in its source — harmless but noisy on Python 3.12+
ENV PYTHONWARNINGS=ignore::SyntaxWarning:whoosh

RUN apk add --no-cache su-exec curl && \
    mkdir -p ${APP_PATH} ${MEMLOG_PATH}

WORKDIR ${APP_PATH}

COPY --from=frontend-build --chmod=777 ${BUILD_DIR}/client/dist ./client/dist
COPY --from=python-deps /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=python-deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

COPY entrypoint.sh healthcheck.sh /
RUN chmod +x /entrypoint.sh /healthcheck.sh

VOLUME /data
ENV MCP_PORT=8090

EXPOSE ${MEMLOG_PORT}/tcp
EXPOSE ${MCP_PORT}/tcp
HEALTHCHECK --interval=60s --timeout=10s CMD /healthcheck.sh
ENTRYPOINT ["/entrypoint.sh"]
