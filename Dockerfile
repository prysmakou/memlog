ARG BUILD_DIR=/build

# Build Container
FROM --platform=$BUILDPLATFORM node:22-alpine AS build

ARG BUILD_DIR

RUN mkdir ${BUILD_DIR}
WORKDIR ${BUILD_DIR}

COPY .htmlnanorc \
    package.json \
    package-lock.json \
    postcss.config.js \
    tailwind.config.js \
    vite.config.js \
    ./

RUN npm ci

COPY client ./client
RUN npm run build

# Runtime Container
FROM python:3.12-slim-bookworm

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

RUN apt update && apt install -y \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR ${APP_PATH}

COPY LICENSE pyproject.toml uv.lock ./
RUN mkdir server && uv pip install --system --no-cache . && rm -rf server

COPY server ./server
COPY --from=build --chmod=777 ${BUILD_DIR}/client/dist ./client/dist

COPY entrypoint.sh healthcheck.sh /
RUN chmod +x /entrypoint.sh /healthcheck.sh

VOLUME /data
EXPOSE ${MEMLOG_PORT}/tcp
HEALTHCHECK --interval=60s --timeout=10s CMD /healthcheck.sh

ENTRYPOINT [ "/entrypoint.sh" ]
