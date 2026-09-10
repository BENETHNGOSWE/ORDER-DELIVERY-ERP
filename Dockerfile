# ============================================================================
# Koda Delivery — production image.
#
# The official frappe/erpnext v16 image PLUS the custom "delivery" app baked
# in (code installed into the bench env + portal assets pre-placed where
# nginx serves them). Every service in docker-compose.yml builds/uses this
# image, so a Coolify redeploy ALWAYS ships with the app — no manual
# get-app/install-app steps, and no more "Internal Server Error" after
# updates. Site data is NOT in the image: it lives in the volumes
# (mariadb-data, sites, redis-queue-data) and survives every deploy.
#
# Base is pinned to the exact version the compose stack used before, so the
# first build after this change is a drop-in replacement.
# ============================================================================
FROM frappe/erpnext:v16.34.1

# ---- stage app code + assets (as root, then hand ownership to frappe) ----
USER root
COPY pyproject.toml /home/frappe/frappe-bench/apps/delivery/pyproject.toml
COPY README.md /home/frappe/frappe-bench/apps/delivery/README.md
COPY delivery /home/frappe/frappe-bench/apps/delivery/delivery
COPY docker/dl-entrypoint.sh /opt/scripts/dl-entrypoint.sh

# Portal static assets:
#  - /usr/share/nginx/html/assets/delivery  -> served by the frontend nginx
#    immediately (html is image content, NOT a volume, so this survives)
#  - /opt/delivery-assets                   -> staging copy the entrypoint
#    wrapper syncs into the shared sites volume on boot
COPY delivery/public /usr/share/nginx/html/assets/delivery
COPY delivery/public /opt/delivery-assets

RUN chmod +x /opt/scripts/dl-entrypoint.sh \
    && chown -R frappe:frappe /home/frappe/frappe-bench/apps/delivery /opt/delivery-assets \
    && chmod -R a+rX /usr/share/nginx/html/assets/delivery

# ---- install the app into the bench python env ----
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN bench pip install -e apps/delivery
