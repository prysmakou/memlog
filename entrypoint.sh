#!/bin/sh

[ "$EXEC_TOOL" ] || EXEC_TOOL=su-exec
[ "$MEMLOG_HOST" ] || MEMLOG_HOST=0.0.0.0
[ "$MEMLOG_PORT" ] || MEMLOG_PORT=8080
[ "$MCP_PORT" ] || MCP_PORT=8090

set -e

echo "'Writing is the geometry of the soul' — Plato"

start_mcp_server() {
    echo "Starting Python MCP server on port ${MCP_PORT}..."
    MEMLOG_URL="http://localhost:${MEMLOG_PORT}" \
    MEMLOG_USERNAME="${MEMLOG_USERNAME}" \
    MEMLOG_PASSWORD="${MEMLOG_PASSWORD}" \
    MEMLOG_TOKEN="${MEMLOG_TOKEN}" \
    "$@" uvicorn memlog_mcp.main:app --host 0.0.0.0 --port "${MCP_PORT}" &
}

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    echo Setting file permissions...
    chown -R ${PUID}:${PGID} ${MEMLOG_PATH}

    start_mcp_server ${EXEC_TOOL} ${PUID}:${PGID}

    echo Starting Memlog as user ${PUID}...
    exec ${EXEC_TOOL} ${PUID}:${PGID} uvicorn memlog.main:app \
        --host ${MEMLOG_HOST} --port ${MEMLOG_PORT}

else
    echo "A user was set by docker, skipping file permission changes."
    start_mcp_server

    echo Starting Memlog as user $(id -u)...
    exec uvicorn memlog.main:app --host ${MEMLOG_HOST} --port ${MEMLOG_PORT}
fi
