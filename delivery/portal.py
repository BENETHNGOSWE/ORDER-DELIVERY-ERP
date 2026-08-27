"""
Website portal hooks.

``get_website_user_home_page`` is a **global** Frappe hook: it runs for every
website login on the site, including users who have nothing to do with delivery.
It must therefore return an empty string for anyone without a delivery role so
Frappe falls back to its own default. Never return a delivery route here unless
the user actually holds one of these roles.

The ``diagnose_home_page`` / ``fix_home_page`` helpers exist because Frappe
caches the home page under the cache key ``"home_page"`` and ``bench
clear-cache`` does not clear it - see :func:`fix_home_page`.
"""
import frappe
from frappe import _

#: delivery role -> landing page
ROLE_HOME = {
    "Delivery Operations": "/operations",
    "Merchant User": "/merchant",
    "Driver": "/driver",
    "Delivery Customer": "/me",
}

#: order matters: the most privileged delivery role wins
PRECEDENCE = ("Delivery Operations", "Merchant User", "Driver", "Delivery Customer")


def get_website_user_home_page(user=None):
    """Send delivery actors to their own portal; leave everyone else alone."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        return ""

    try:
        roles = set(frappe.get_roles(user))
    except Exception:
        return ""

    for role in PRECEDENCE:
        if role in roles:
            return ROLE_HOME[role]

    # not a delivery user - let Frappe use its own default
    return ""


# ---------------------------------------------------------------------------
# home-page diagnostics
# ---------------------------------------------------------------------------
def diagnose_home_page():
    """
    Report what Frappe will serve at ``/`` and whether that route resolves.

    ``Website Settings.validate_home_page`` silently blanks an invalid value, so
    a write that appears to succeed can store an empty string. This prints the
    truth.
    """
    from frappe.website.utils import get_home_page
    from frappe.website.path_resolver import PathResolver

    stored = frappe.db.get_single_value("Website Settings", "home_page")
    resolved = get_home_page()

    report = {
        "stored_home_page": stored,
        "resolved_home_page": resolved,
        "stored_is_valid": bool(stored) and PathResolver(stored).is_valid_path(),
        "resolved_is_valid": bool(resolved) and PathResolver(resolved).is_valid_path(),
    }
    for key, value in report.items():
        print("{0}: {1}".format(key, value))
    return report


def fix_home_page(home_page="home"):
    """
    Point ``/`` at ``home`` and drop the cached value.

    ``get_home_page`` caches under ``"home_page"`` (see
    ``frappe/website/router.py``). ``bench clear-cache`` does **not** clear that
    key, so a corrected setting has no effect until it is deleted explicitly.
    """
    from frappe.website.path_resolver import PathResolver

    if not PathResolver(home_page).is_valid_path():
        frappe.throw(_("{0} is not a valid website route.").format(home_page),
                     title=_("Invalid Home Page"))

    frappe.db.set_single_value("Website Settings", "home_page", home_page)
    frappe.cache.delete_value("home_page")
    frappe.db.commit()
    print("home_page set to {0} and cache cleared".format(home_page))
    return home_page


@frappe.whitelist(allow_guest=True)
def session_csrf():
    """
    Return the session CSRF token for the standalone portal pages.

    The portal pages deliberately do not extend Frappe's base template (that
    would couple them to the host site's theme), so they get no server-rendered
    token. Rather than depend on one accessor - which differs between Frappe
    versions and raises *inside the template* when it is wrong, taking the
    whole page down with it - each known accessor is tried in turn.

    Fetched over GET, which Frappe does not CSRF-protect.
    """
    accessors = (
        lambda: frappe.sessions.get_csrf_token(),
        lambda: frappe.session.csrf_token,
        lambda: frappe.local.session.data.csrf_token,
    )
    for accessor in accessors:
        try:
            token = accessor()
        except Exception:
            continue
        if token:
            return token
    return ""
