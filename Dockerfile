# Production image for ERPNext v16 + the custom "delivery" (Delivery Logistics) app.
# Built by Coolify from this repo. All Frappe services (backend, workers,
# scheduler, websocket, frontend/nginx) use this SAME image.
#
# Why the folder rename: the GitHub repo is "ORDER-DELIVERY-ERP", so `bench get-app`
# clones it to apps/ORDER-DELIVERY-ERP, but the Frappe app module is "delivery".
# Frappe's asset builder (esbuild) keys paths by the folder name, which then
# mismatches the --app name and crashes with "paths[0] ... Received undefined".
# Renaming the cloned folder to `delivery` makes the folder and module names match.
ARG FRAPPE_TAG=v16.34.1
FROM frappe/erpnext:${FRAPPE_TAG}

# Public repo is the default. Set GIT_TOKEN in Coolify "Build Variables" if private.
ARG GIT_TOKEN=
ARG APP_REPO=https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
ARG APP_BRANCH=main

USER frappe
WORKDIR /home/frappe/frappe-bench

# 1) install the app but SKIP the automatic asset build (it crashes due to the
#    folder/module name mismatch described above),
# 2) rename the cloned folder to the real module name "delivery",
# 3) reinstall the package in editable mode from the new path,
# 4) build assets for the app (no JS bundle, so this only links assets),
# 5) link the app's public/static files into the shared sites/assets dir so the
#    nginx service serves /assets/delivery/*.
RUN set -eux; \
    if [ -n "$GIT_TOKEN" ]; then \
      APP_URL="https://x-access-token:${GIT_TOKEN}@${APP_REPO#https://}"; \
    else \
      APP_URL="${APP_REPO}"; \
    fi; \
    bench get-app --skip-assets --branch "${APP_BRANCH}" "${APP_URL}"; \
    rm -rf apps/delivery; \
    mv apps/ORDER-DELIVERY-ERP apps/delivery; \
    bench pip install --no-cache-dir -e apps/delivery; \
    bench build --app delivery || true; \
    mkdir -p sites/assets; \
    ln -sfn ../../apps/delivery/delivery/public sites/assets/delivery

# default command is inherited from the base image (gunicorn web server);
# docker-compose overrides it per service (nginx-entrypoint, worker, schedule, ...).
