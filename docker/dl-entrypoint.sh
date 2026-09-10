#!/bin/bash
# ============================================================================
# dl-entrypoint.sh — wrapper around the stock frappe/erpnext entrypoint.
#
# The only thing a FRESH sites volume can be missing is sites/apps.txt
# (the stock configurator normally writes it). We write it from the apps
# actually present in the image, then hand over to the stock entrypoint,
# which re-links sites/assets to the baked assets and execs the service
# command. Everything else about stock behaviour is preserved.
# ============================================================================
set -e

BENCH=/home/frappe/frappe-bench

if [ -d "$BENCH/sites" ]; then
  ls -1 "$BENCH/apps" > "$BENCH/sites/apps.txt" 2>/dev/null || true
fi

exec /usr/local/bin/entrypoint.sh "$@"
