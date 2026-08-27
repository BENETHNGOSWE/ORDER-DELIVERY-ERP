#!/usr/bin/env bash
# =============================================================================
#  Delivery & Logistics - one-shot installer for a frappe_docker container
#
#  Usage (inside the container, as the `frappe` user):
#      ./install.sh                      # install on the only/active site
#      ./install.sh erpnext.example.com  # install on a named site
#      ./install.sh --demo               # also seed demo users + catalogue
#
#  Designed around the frappe_docker production constraints:
#    * `bench get-app`   is not available  -> the app is copied in directly
#    * `bench build`     is forbidden      -> assets are copied, not built
#    * `bench restart`   does not work     -> restart the container instead
# =============================================================================
set -euo pipefail

BENCH="${BENCH_DIR:-$HOME/frappe-bench}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/delivery"
SEED_DEMO=0
SITE=""

for arg in "$@"; do
  case "$arg" in
    --demo) SEED_DEMO=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) SITE="$arg" ;;
  esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  OK\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m  XX\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- environment
[ -d "$BENCH" ]              || die "no bench at $BENCH (set BENCH_DIR)"
[ -f "$SRC/pyproject.toml" ] || die "app source not found at $SRC"
command -v bench >/dev/null 2>&1 || export PATH="$BENCH/env/bin:$PATH"
command -v bench >/dev/null 2>&1 || die "bench not on PATH"

cd "$BENCH"

# ---------------------------------------------------------------- resolve site
if [ -z "$SITE" ]; then
  if [ -f sites/currentsite.txt ]; then
    SITE="$(cat sites/currentsite.txt)"
  else
    found="$(find sites -maxdepth 1 -mindepth 1 -type d -name '*.*' -printf '%f\n' 2>/dev/null | sort)"
    count="$(printf '%s\n' "$found" | grep -c . || true)"
    [ "$count" -eq 1 ] || die "cannot guess the site; pass it: ./install.sh <site>
  candidates: $found"
    SITE="$found"
  fi
fi
[ -d "sites/$SITE" ] || die "site '$SITE' not found under sites/"
say "bench: $BENCH"
say "site:  $SITE"

# ---------------------------------------------------------------- versions
# `bench execute` needs a callable, and frappe.__version__ is a string, so
# the version is read from `list-apps`, which prints "frappe 16.31.0 version-16".
FRAPPE_VER="$(bench --site "$SITE" list-apps 2>/dev/null \
  | awk '/^frappe[ \t]/ {print $2; exit}')"
FRAPPE_VER="${FRAPPE_VER:-unknown}"
say "frappe: $FRAPPE_VER"
case "$FRAPPE_VER" in
  15.*|16.*|17.*) ok "supported Frappe major version" ;;
  unknown)        warn "could not read the Frappe version" ;;
  *)              warn "built and tested on Frappe 16 / ERPNext 16; you appear to
     be on $FRAPPE_VER. Proceeding, but this combination is untested." ;;
esac

# ---------------------------------------------------------------- copy app
if [ -e "$BENCH/apps/delivery" ]; then
  say "apps/delivery already present - refreshing code"
  rm -rf "$BENCH/apps/delivery"
fi
cp -r "$SRC" "$BENCH/apps/delivery"
ok "app copied to apps/delivery"

grep -qx "delivery" sites/apps.txt 2>/dev/null || {
  echo "delivery" >> sites/apps.txt
  ok "added 'delivery' to sites/apps.txt"
}

# ---------------------------------------------------------------- sanity check
"$BENCH/env/bin/python" -c "
import compileall, sys
sys.exit(0 if compileall.compile_dir('$BENCH/apps/delivery/delivery', quiet=2) else 1)
" || die "app failed to byte-compile"
ok "app byte-compiles cleanly"

# ---------------------------------------------------------------- install
if bench --site "$SITE" list-apps 2>/dev/null | grep -qx "delivery"; then
  say "app already installed - migrating schema"
  bench --site "$SITE" migrate
  ok "migrated"
else
  say "installing app (runs after_install: roles, settings, zones, weight bands)"
  bench --site "$SITE" install-app delivery
  ok "installed"
fi

# ---------------------------------------------------------------- assets
# `bench build` must NOT run in a production container - it corrupts the shared
# assets volume. The portal ships plain (non-bundled) JS/CSS, so copying them
# into the assets volume is exactly what a build would have produced.
mkdir -p "sites/assets/delivery"
cp -r "$BENCH/apps/delivery/delivery/public/." "sites/assets/delivery/"
ok "portal assets -> sites/assets/delivery"

for f in js/delivery_portal.js css/delivery_portal.css; do
  [ -f "sites/assets/delivery/$f" ] || die "asset missing: $f"
done
ok "assets verified"

# ---------------------------------------------------------------- cache
bench --site "$SITE" clear-cache
bench --site "$SITE" clear-website-cache
ok "caches cleared"

# ---------------------------------------------------------------- demo data
if [ "$SEED_DEMO" -eq 1 ]; then
  say "seeding demo data"
  bench --site "$SITE" execute delivery.demo_data.seed
  ok "demo data seeded"
fi

# ---------------------------------------------------------------- report
echo
ok "Delivery & Logistics installed on $SITE"
cat <<EOF

  Portal routes (namespaced, nothing else on the site is touched):
    /delivery              landing page
    /delivery/menu         food & retail catalogue
    /delivery/cart         cart + checkout
    /delivery/parcel       parcel request
    /delivery/transport    negotiated transport
    /delivery/track        public tracking (?ref=...)
    /delivery/me           customer dashboard
    /delivery/merchant     merchant portal
    /delivery/operations   operations console
    /delivery/driver       driver dashboard

  Desk: /app/delivery-order  (and the other Delivery Logistics doctypes)

  LAST STEP - restart the container. 'bench restart' does not work here:

      docker restart $(hostname)

  Then load https://<your-domain>/delivery
EOF
