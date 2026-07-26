#!/usr/bin/env bash
set -euo pipefail

URL="http://localhost:8800/"
TIMEOUT=5

if ! curl -fsS --max-time "$TIMEOUT" -o /dev/null "$URL"; then
    logger -t iris-watchdog "Iris ne répond pas sur $URL, redémarrage du service"
    systemctl restart iris.service
fi
