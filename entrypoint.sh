#!/bin/sh

[ "$EXEC_TOOL" ] || EXEC_TOOL=gosu
[ "$MEMLOG_HOST" ] || MEMLOG_HOST=0.0.0.0
[ "$MEMLOG_PORT" ] || MEMLOG_PORT=8080

set -e

echo "\
======================================
========== Welcome to Memlog =========
======================================
──────────────────────────────────────
"

memlog_command="python -m \
                  uvicorn \
                  main:app \
                  --app-dir server \
                  --host ${MEMLOG_HOST} \
                  --port ${MEMLOG_PORT} \
                  --proxy-headers \
                  --forwarded-allow-ips '*'"

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    echo Setting file permissions...
    chown -R ${PUID}:${PGID} ${MEMLOG_PATH}

    echo Starting Memlog as user ${PUID}...
    exec ${EXEC_TOOL} ${PUID}:${PGID} ${memlog_command}

else
    echo "A user was set by docker, skipping file permission changes."
    echo Starting Memlog as user $(id -u)...
    exec ${memlog_command}
fi
