app_name = "delivery"
app_title = "Delivery & Logistics"
app_publisher = "Swift Logistics"
app_description = (
    "Multi-Service Delivery & Logistics Platform: Food, Retail, Parcel and "
    "Negotiated Transport - built on ERPNext / Frappe."
)
app_email = "ops@swiftlogistics.test"
app_license = "MIT"
app_version = "1.1.0"
required_apps = ["frappe"]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Only the roles are fixtures. Zones and weight categories are operational data
# that belongs to the site, not to the app, so they are deliberately NOT
# exported - `bench export-fixtures` must not dump a customer's own zones.
fixtures = [
    {"dt": "Role", "filters": [["name", "in", [
        "Delivery Operations", "Merchant User", "Driver", "Delivery Customer"]]]},
]

after_install = "delivery.install.after_install"

# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------
# Intentionally EMPTY. The three service documents implement their logic as
# Document methods (validate/after_insert), which is the idiomatic path. Wiring
# doc_events to the same functions as well would run the validate pass twice and
# draw merchant stock down twice per order.
doc_events = {}

# ---------------------------------------------------------------------------
# Portal / website
# ---------------------------------------------------------------------------
# All portal routes are namespaced under /delivery/ so this app can be dropped
# onto an existing ERPNext site without claiming generic routes such as /,
# /home, /track, /me or /cart that the site may already use.
#
#   /delivery            landing page
#   /delivery/menu       merchant catalogue
#   /delivery/cart       cart + checkout
#   /delivery/parcel     parcel request
#   /delivery/transport  negotiated transport
#   /delivery/track      public tracking (?ref=...)
#   /delivery/me         customer dashboard
#   /delivery/merchant   merchant portal
#   /delivery/operations operations console
#   /delivery/driver     driver dashboard
#
# No `website_redirects` and no `base_template` here on purpose:
#   * a root redirect would hijack the site's own homepage;
#   * `base_template` overrides the GLOBAL Frappe base template, desk included,
#     and would restyle the whole ERPNext instance.
# Portal pages pull in their own CSS/JS instead of using web_include_js/css,
# which would inject them into every page on the site.
website_route_rules = []

# delivery role -> landing page (global hook, but only our own role names)
role_home_page = {
    "Delivery Operations": "/delivery/operations",
    "Merchant User": "/delivery/merchant",
    "Driver": "/delivery/driver",
    "Delivery Customer": "/delivery/me",
}

# Returns "" for anyone without a delivery role, so normal website logins on
# this site are completely unaffected.
website_user_home_page = "delivery.portal.get_website_user_home_page"

# ---------------------------------------------------------------------------
# Permissions: portal users may only touch their own service documents
# ---------------------------------------------------------------------------
has_permission = {
    "Delivery Order": "delivery.permissions.order_permission",
    "Parcel Request": "delivery.permissions.parcel_permission",
    "Transport Request": "delivery.permissions.transport_permission",
    "Payment Transaction": "delivery.permissions.payment_permission",
}

# ---------------------------------------------------------------------------
# Scheduler - one job only; the SRS web scope needs no other background work
# ---------------------------------------------------------------------------
scheduler_events = {
    "hourly": [
        "delivery.tasks.expire_transport_quotes",
    ],
}
