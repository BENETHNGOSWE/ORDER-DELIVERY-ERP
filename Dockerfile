# Production image for ERPNext v16 + the custom "delivery" (Delivery Logistics) app.
# Built automatically by Coolify from this repo. All long-running Frappe services
# (backend, workers, scheduler) use this same image.
#
# Pin FRAPPE_TAG to the newest v16 tag from https://hub.docker.com/r/frappe/erpnext/tags
ARG FRAPPE_TAG=v16.x
FROM frappe/erpnext:${FRAPPE_TAG}

# Optional: if your GitHub repo is PRIVATE, pass a GitHub token as a build secret/arg
# in Coolify (variable GIT_TOKEN). If the repo is public you can leave it empty.
ARG GIT_TOKEN=
ARG APP_REPO=https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
ARG APP_BRANCH=main

USER frappe
RUN if [ -n "$GIT_TOKEN" ]; then \
      bench get-app --branch "${APP_BRANCH}" "https://x-access-token:${GIT_TOKEN}@${APP_REPO#https://}"; \
    else \
      bench get-app --branch "${APP_BRANCH}" "${APP_REPO}"; \
    fi

# default command is inherited from the base image (gunicorn web server)
