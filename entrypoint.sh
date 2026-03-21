#!/bin/sh

[ "$EXEC_TOOL" ] || EXEC_TOOL=gosu
[ "$MEMLOG_HOST" ] || MEMLOG_HOST=0.0.0.0
[ "$MEMLOG_PORT" ] || MEMLOG_PORT=8080
[ "$MCP_PORT" ] || MCP_PORT=8090

set -e

echo "\
======================================
========== Welcome to Memlog =========
======================================
  'Writing is the geometry of the soul'
                              — Plato
──────────────────────────────────────
"

start_mcp_server() {
    if [ -x ${APP_PATH}/mcp-server ]; then
        echo "Starting Rust MCP server on port ${MCP_PORT}..."
        MEMLOG_URL="http://localhost:${MEMLOG_PORT}" \
        MCP_BIND="0.0.0.0:${MCP_PORT}" \
        MEMLOG_USERNAME="${MEMLOG_USERNAME}" \
        MEMLOG_PASSWORD="${MEMLOG_PASSWORD}" \
        MEMLOG_TOKEN="${MEMLOG_TOKEN}" \
        "$@" ${APP_PATH}/mcp-server &
    fi
}

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    echo Setting file permissions...
    chown -R ${PUID}:${PGID} ${MEMLOG_PATH}

    start_mcp_server ${EXEC_TOOL} ${PUID}:${PGID}

    echo Starting Memlog as user ${PUID}...
    exec ${EXEC_TOOL} ${PUID}:${PGID} ${APP_PATH}/memlog-server

else
    echo "A user was set by docker, skipping file permission changes."
    start_mcp_server

    echo Starting Memlog as user $(id -u)...
    exec ${APP_PATH}/memlog-server
fi
