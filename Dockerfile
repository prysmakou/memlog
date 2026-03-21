ARG BUILD_DIR=/build

# Frontend build
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

# Rust build (MCP server + backend)
FROM rust:bookworm AS rust-build

WORKDIR /build

# Cache workspace dependencies with stub binaries
COPY Cargo.toml ./
COPY mcp-server-rs/Cargo.toml mcp-server-rs/Cargo.lock ./mcp-server-rs/
COPY server-rs/Cargo.toml ./server-rs/
RUN mkdir -p mcp-server-rs/src server-rs/src \
    && echo 'fn main() {}' > mcp-server-rs/src/main.rs \
    && echo 'fn main() {}' > server-rs/src/main.rs
RUN cargo build --release
RUN rm -f target/release/deps/memlog_mcp* target/release/deps/memlog_server*

# Build the real binaries
COPY mcp-server-rs/src ./mcp-server-rs/src
COPY server-rs/src ./server-rs/src
RUN cargo build --release

# Runtime Container
FROM debian:bookworm-slim

ARG BUILD_DIR

ENV PUID=1000
ENV PGID=1000
ENV EXEC_TOOL=gosu
ENV MEMLOG_HOST=0.0.0.0
ENV MEMLOG_PORT=8080

ENV APP_PATH=/app
ENV MEMLOG_PATH=/data

RUN mkdir -p ${APP_PATH}
RUN mkdir -p ${MEMLOG_PATH}

RUN apt-get update && apt-get install -y \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR ${APP_PATH}

COPY --from=frontend-build --chmod=777 ${BUILD_DIR}/client/dist ./client/dist
COPY --from=rust-build --chmod=755 /build/target/release/memlog-mcp ./mcp-server
COPY --from=rust-build --chmod=755 /build/target/release/memlog-server ./memlog-server

COPY entrypoint.sh healthcheck.sh /
RUN chmod +x /entrypoint.sh /healthcheck.sh

VOLUME /data
ENV MCP_PORT=8090

EXPOSE ${MEMLOG_PORT}/tcp
EXPOSE ${MCP_PORT}/tcp
HEALTHCHECK --interval=60s --timeout=10s CMD /healthcheck.sh

ENTRYPOINT [ "/entrypoint.sh" ]
