#!/bin/bash
# ============================================================================
# dl-entrypoint.sh — wrapper around the stock frappe/erpnext entrypoint.
#
# Runs before every service (frontend, backend, worker, scheduler, websocket)
# and makes sure the SHARED SITES VOLUME always knows about the baked-in app:
#   1. sites/apps.txt lists every app in the image (frappe, erpnext, delivery)
#   2. sites/assets/delivery holds the portal static assets
# The sites volume persists across deploys, but this keeps a FRESH volume
# correct too (e.g. if you ever recreate the stack from scratch).
# Then it hands over to the image's normal entrypoint, so all original
# behaviours (nginx, gunicorn, scheduler, worker, socketio) are unchanged.
# ============================================================================
set -e

BENCH=/home/frappe/frappe-bench
SRC=/opt/delivery-assets

if [ -d "$BENCH/sites" ]; then
  # apps.txt: one app name per line, from what's actually installed
  ls -1 "$BENCH/apps" > "$BENCH/sites/apps.txt" 2>/dev/null || true

  # portal assets into the shared volume (best-effort, never blocks boot)
  if [ -d "$SRC" ]; then
    mkdir -p "$BENCH/sites/assets/delivery" 2>/dev/null || true
    cp -r "$SRC/." "$BENCH/sites/assets/delivery/" 2>/dev/null || true
  fi
fi

exec /usr/local/bin/entrypoint.sh "$@"
