# ============================================================================
# Koda Delivery — production image.
#
# The official frappe/erpnext v16 image PLUS the custom "delivery" app baked
# in (code installed into the bench env + portal assets pre-placed where the
# image's nginx actually serves them). Every service in docker-compose.yml
# builds/uses this image, so a Coolify redeploy ALWAYS ships with the app —
# no manual get-app/install-app steps. Site data is NOT in the image: it
# lives in the volumes (mariadb-data, sites, redis-queue-data) and survives
# every deploy.
#
# Asset handling follows the stock image pattern exactly: the stock
# entrypoint (main-entrypoint.sh) re-links sites/assets -> the baked
# /home/frappe/frappe-bench/assets on EVERY boot, and the internal nginx
# serves /assets from the sites root (through that symlink). So portal
# static files are baked into /home/frappe/frappe-bench/assets/delivery.
# ============================================================================
FROM frappe/erpnext:v16.34.1

# ---- stage app code (as root, then hand ownership to frappe) ----
USER root
COPY pyproject.toml /home/frappe/frappe-bench/apps/delivery/pyproject.toml
COPY README.md /home/frappe/frappe-bench/apps/delivery/README.md
COPY delivery /home/frappe/frappe-bench/apps/delivery/delivery
COPY docker/dl-entrypoint.sh /opt/scripts/dl-entrypoint.sh

# Portal static assets into the BAKED assets dir (the target of the
# sites/assets symlink the stock entrypoint creates on every boot).
COPY delivery/public /home/frappe/frappe-bench/assets/delivery

RUN chmod +x /opt/scripts/dl-entrypoint.sh \
    && chown -R frappe:frappe /home/frappe/frappe-bench/apps/delivery \
                              /home/frappe/frappe-bench/assets/delivery

# ---- install the app into the bench python env ----
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN bench pip install -e apps/delivery
