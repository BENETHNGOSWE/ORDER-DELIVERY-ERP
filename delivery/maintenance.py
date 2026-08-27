"""
One-off maintenance helpers for the delivery install.

    bench --site <site> execute delivery.maintenance.audit_pages
    bench --site <site> execute delivery.maintenance.unpublish_broken_pages
    bench --site <site> execute delivery.maintenance.recent_errors
"""
import os
import re

import frappe

INCLUDE_RE = re.compile(r'{%\s*(?:include|extends)\s+"([^"]+)"')


def _template_exists(path):
    """Would Jinja be able to resolve this template path in any installed app?"""
    for app in frappe.get_installed_apps():
        base = frappe.get_app_path(app)
        for candidate in (path,
                          os.path.join("templates", path),
                          os.path.join("www", path)):
            if os.path.isfile(os.path.join(base, candidate)):
                return True
    return False


def _scan():
    broken = []
    for r in frappe.get_all(
        "Web Page",
        fields=["name", "route", "published", "content_type", "dynamic_template",
                "main_section", "main_section_html", "main_section_md"],
    ):
        body = r.main_section or r.main_section_html or r.main_section_md or ""
        for tpl in INCLUDE_RE.findall(body):
            if not _template_exists(tpl):
                broken.append({"name": r.name, "route": r.route,
                               "published": r.published, "missing": tpl})
    return broken


def audit_pages():
    """List every Web Page whose template include cannot be resolved."""
    broken = _scan()
    if not broken:
        print("No Web Page records reference a missing template.")
        return []
    print("Web Page records whose template include cannot be resolved:")
    for b in broken:
        print("  {0:24s} route={1:22s} published={2}  missing={3}".format(
            b["name"], b["route"], b["published"], b["missing"]))
    print()
    print("Routes that collide with the delivery app portal:")
    for b in broken:
        if b["route"] == "delivery" or str(b["route"]).startswith("delivery/"):
            print("  {0:24s} -> /{1}".format(b["name"], b["route"]))
    return broken


def unpublish_broken_pages():
    """Unpublish those pages. Reversible: set published back to 1 to restore."""
    broken = _scan()
    changed = []
    for b in broken:
        if b["published"]:
            frappe.db.set_value("Web Page", b["name"], "published", 0)
            changed.append(b["name"])

    frappe.db.commit()
    # home_page is cached under its own key and clear-cache does not drop it
    frappe.cache.delete_value("home_page")
    frappe.clear_cache()

    print("Unpublished {0} Web Page record(s):".format(len(changed)))
    for name in changed:
        print("  - " + name)
    print()
    print("Now run: bench --site <site> clear-website-cache")
    return changed


def recent_errors(limit=5):
    """Print the tail of the most recent Error Log entries."""
    rows = frappe.get_all("Error Log",
                          fields=["name", "creation", "method", "error"],
                          order_by="creation desc", limit=int(limit))
    if not rows:
        print("No error log entries.")
        return 0
    for r in rows:
        print("=" * 70)
        print("{0}  {1}  {2}".format(r.creation, r.name, r.method))
        print((r.error or "")[-1200:])
    return len(rows)


def home_page():
    """Report what the site serves at /."""
    from frappe.website.utils import get_home_page
    stored = frappe.db.get_single_value("Website Settings", "home_page")
    print("Website Settings.home_page = {0!r}".format(stored))
    print("resolved home page         = {0!r}".format(get_home_page()))
    print("Web Page at that route     = {0!r}".format(
        frappe.db.get_value("Web Page", {"route": stored}, "name")))
    print("www/ page at that route    = {0}".format(
        "yes" if os.path.isfile(os.path.join(
            frappe.get_app_path("delivery"), "www", str(stored) + ".html")) or
        os.path.isfile(os.path.join(
            frappe.get_app_path("delivery"), "www", str(stored), "index.html"))
        else "no"))


def probe_csrf():
    """Which expression actually yields the CSRF token on this Frappe version?"""
    attempts = [
        ("frappe.sessions.get_csrf_token()",
         lambda: frappe.sessions.get_csrf_token()),
        ("frappe.session.csrf_token",
         lambda: frappe.session.csrf_token),
        ("frappe.local.session.data.csrf_token",
         lambda: frappe.local.session.data.csrf_token),
    ]
    for label, fn in attempts:
        try:
            value = fn()
            print("  OK    {0:42s} -> {1}...".format(label, str(value)[:10]))
        except Exception as e:
            print("  FAIL  {0:42s} -> {1}: {2}".format(label, type(e).__name__, e))


def probe_templates():
    """Render every portal page through Frappe's own Jinja env, report failures."""
    from frappe.utils.jinja import get_jenv

    jenv = get_jenv()
    root = os.path.join(frappe.get_app_path("delivery"), "www", "delivery")
    for f in sorted(os.listdir(root)):
        if not f.endswith(".html"):
            continue
        rel = "www/delivery/" + f
        try:
            jenv.get_template(rel).render({"page_title": "probe"})
            print("  OK    " + rel)
        except Exception as e:
            print("  FAIL  {0}: {1}: {2}".format(rel, type(e).__name__, str(e)[:300]))
