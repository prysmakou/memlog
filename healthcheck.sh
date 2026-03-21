#!/bin/sh

curl -f http://localhost:${MEMLOG_PORT}${MEMLOG_PATH_PREFIX}/health || exit 1
