# ============================================================================
# OPTIONAL custom image — NOT used by docker-compose.yml.
#
# The production stack in docker-compose.yml runs the OFFICIAL frappe/erpnext
# image directly and does NOT build this file. You do not need this Dockerfile
# to get Frappe running on your domain.
#
# After Frappe is running and you have created the site, install the custom
# "delivery" app yourself from the backend container terminal:
#
#   bench --site delivery.kodatechnologies.co.tz install-app delivery   # if already installed locally
#   # or, to pull this app from GitHub at runtime:
#   bench get-app --skip-assets https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
#   mv apps/ORDER-DELIVERY-ERP apps/delivery        # repo folder must match the module name
#   bench pip install -e apps/delivery
#   bench --site delivery.kodatechnologies.co.tz install-app delivery
#
# (Only use this Dockerfile later if you want to bake the custom app into the
#  image so it survives container recreation without manual setup.)
# ============================================================================
FROM frappe/erpnext:v16.34.1
