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

# ── Stage 2: Rust MCP binary (musl static, runs on Alpine) ───────────────────
FROM rust:alpine AS rust-build

RUN apk add --no-cache musl-dev

WORKDIR /build

# Cache workspace deps with stub binaries before copying real source
COPY Cargo.toml ./
COPY mcp-server-rs/Cargo.toml mcp-server-rs/Cargo.lock ./mcp-server-rs/
COPY server-rs/Cargo.toml ./server-rs/
RUN mkdir -p mcp-server-rs/src server-rs/src \
    && echo 'fn main() {}' > mcp-server-rs/src/main.rs \
    && echo 'fn main() {}' > server-rs/src/main.rs
RUN cargo build --release -p memlog-mcp
RUN rm -f target/release/deps/memlog_mcp*

COPY mcp-server-rs/src ./mcp-server-rs/src
RUN cargo build --release -p memlog-mcp

# ── Stage 3: Python deps ──────────────────────────────────────────────────────
FROM python:3.13-alpine AS python-deps

# gcc + musl-dev needed to compile some Python C extensions (e.g. cffi)
RUN apk add --no-cache gcc musl-dev

WORKDIR /build

COPY server/ ./server/
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache ./server

# ── Stage 4: Runtime ──────────────────────────────────────────────────────────
FROM python:3.13-alpine

ARG BUILD_DIR

ENV PUID=1000
ENV PGID=1000
ENV EXEC_TOOL=su-exec
ENV MEMLOG_HOST=0.0.0.0
ENV MEMLOG_PORT=8080

ENV APP_PATH=/app
ENV MEMLOG_PATH=/data

RUN apk add --no-cache su-exec curl && \
    mkdir -p ${APP_PATH} ${MEMLOG_PATH}

WORKDIR ${APP_PATH}

COPY --from=frontend-build --chmod=777 ${BUILD_DIR}/client/dist ./client/dist
COPY --from=rust-build --chmod=755 /build/target/release/memlog-mcp ./mcp-server
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
