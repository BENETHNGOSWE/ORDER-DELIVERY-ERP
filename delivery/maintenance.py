"""
One-off maintenance helpers for the delivery install.

    bench --site <site> execute delivery.maintenance.audit_pages
    bench --site <site> execute delivery.maintenance.unpublish_broken_pages
    bench --site <site> execute delivery.maintenance.recent_errors
"""
import json
import os
import re
import uuid

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


def make_portal_images_public(dry_run=False):
	"""
	Move every portal-facing image from private to public storage.

	Symptom this fixes: photos show when you are logged in on your computer but
	are broken for guests on mobile. Files uploaded through Desk default to
	PRIVATE (/private/files/...), which Frappe only serves with a valid session.
	The public portal must use /files/... so anonymous visitors can load them.

	Covers Merchant.logo, Home Banner.image and DL Menu Item.item_image. For each
	private file it moves the bytes from sites/<site>/private/files to
	sites/<site>/public/files, flips the File record is_private=0, and rewrites
	the stored URL. Idempotent - already-public images are reported and skipped.

	    bench --site <site> execute delivery.maintenance.make_portal_images_public
	    bench --site <site> execute delivery.maintenance.make_portal_images_public \
	      --kwargs '{"dry_run": true}'
	"""
	import shutil

	# (DocType, image field, label)
	targets = [
		("Merchant", "logo", "merchant logo"),
		("Home Banner", "image", "home banner"),
		("DL Menu Item", "item_image", "menu item image"),
	]

	site_path = frappe.get_site_path()
	public_files_dir = os.path.join(site_path, "public", "files")
	private_files_dir = os.path.join(site_path, "private", "files")

	made_public, already_public, missing, no_file = [], [], [], []

	for doctype, field, label in targets:
		rows = frappe.get_all(doctype, fields=["name", field])
		for r in rows:
			url = (r.get(field) or "").strip()
			if not url:
				continue

			if "/private/files/" not in url:
				already_public.append("{0} {1}".format(label, r.name))
				continue

			# find the File record by its stored URL
			file_name = frappe.db.get_value("File", {"file_url": url},
			                                ["name", "file_name", "is_private"],
			                                as_dict=True)
			if not file_name:
				no_file.append("{0} {1}: {2}".format(label, r.name, url))
				continue

			old_rel = url.split("/private/files/", 1)[1]
			new_url = "/files/" + old_rel
			src = os.path.join(private_files_dir, old_rel)
			dst = os.path.join(public_files_dir, old_rel)

			if dry_run:
				print("[dry-run] would make public: {0} {1} -> {2}".format(
					label, r.name, new_url))
				made_public.append(r.name)
				continue

			if not os.path.isfile(src):
				missing.append("{0} {1}: file missing on disk {2}".format(label, r.name, src))
				continue

			os.makedirs(public_files_dir, exist_ok=True)
			shutil.move(src, dst)

			# rewrite File record + the referencing DocType field
			frappe.db.set_value("File", file_name.name,
			                    {"is_private": 0, "file_url": new_url},
			                    update_modified=False)
			frappe.db.set_value(doctype, r.name, field, new_url,
			                    update_modified=False)
			made_public.append("{0} {1}".format(label, r.name))

	if not dry_run:
		frappe.db.commit()

	print()
	print("Portal image visibility results:")
	print("  made public : {0}".format(len(made_public)))
	for m in made_public:
		print("      + " + m)
	print("  already public (skipped): {0}".format(len(already_public)))
	if missing:
		print("  MISSING ON DISK ({0}):".format(len(missing)))
		for m in missing:
			print("      ! " + m)
	if no_file:
		print("  no File record ({0}):".format(len(no_file)))
		for m in no_file:
			print("      ? " + m)
	if not dry_run and made_public:
		print()
		print("Done. Guests (mobile, not logged in) can now load these images.")
	return {"made_public": made_public, "already_public": already_public,
	        "missing": missing, "no_file_record": no_file}


def bulk_attach_images(folder="/home/frappe/product-images", match_by=None):
	"""
	Attach product photos in bulk from a folder to DL Menu Item records.

	Put your images in one folder, named by the ITEM CODE (or a slug of the
	product name), e.g.

	    ~/product-images/SG-PILAU.jpg
	    ~/product-images/KM-RICE-5KG.png
	    ~/product-images/mc-coffee.webp
	    ~/product-images/pilau-special.jpg   # matches product name

	Run:
	    bench --site delivery.localhost execute \
	      delivery.maintenance.bulk_attach_images \
	      --kwargs '{"folder":"/home/eveneth_beneth/product-images"}'

	Matching: file stem (lowercased, stripped) is compared against the item
	code and a slug of the item name. Existing images are skipped unless you
	force re-run. Sets published=1 as well so items always show.
	"""
	import unicodedata

	def slug(s):
		s = (s or "").lower()
		s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
		return "".join(ch if ch.isalnum() else "-" for ch in s).strip("-")

	if not os.path.isdir(folder):
		frappe.throw("Folder not found: {0}".format(folder))

	exts = (".png", ".jpg", ".jpeg", ".webp")
	files = [f for f in os.listdir(folder) if f.lower().endswith(exts)]
	by_stem = {}
	for f in files:
		stem = os.path.splitext(f)[0].strip().lower()
		by_stem.setdefault(stem, f)

	items = frappe.get_all("DL Menu Item",
		fields=["name", "item_code", "item_name", "item_image"])

	updated, missing, skipped = [], [], []
	for it in items:
		candidates = [
			(it.item_code or "").strip().lower(),
			slug(it.item_name),
		]
		fname = None
		for c in candidates:
			if c and c in by_stem:
				fname = by_stem[c]; break
		if not fname:
			missing.append(it.item_code or it.name)
			continue
		if it.item_image:
			skipped.append(it.item_code or it.name)
			continue

		path = os.path.join(folder, fname)
		with open(path, "rb") as fh:
			content = fh.read()
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": fname,
			"attached_to_doctype": "DL Menu Item",
			"attached_to_name": it.name,
			"attached_to_field": "item_image",
			"is_private": 0,
			"content": content,
		}).insert(ignore_permissions=True)
		frappe.db.set_value("DL Menu Item", it.name,
		                    {"item_image": file_doc.file_url, "published": 1},
		                    update_modified=False)
		updated.append(it.item_code or it.name)

	frappe.db.commit()
	print("Attached {0} image(s), skipped {1} (already had image), "
	      "{2} item(s) with no matching file.".format(len(updated), len(skipped), len(missing)))
	if missing:
		print("No image file for: " + ", ".join(missing))
	return {"updated": updated, "skipped": skipped, "missing": missing}


# ---------------------------------------------------------------------------
# Default home-page categories ("Shop by category") - seeded once, then the
# admin manages them from Desk -> Item Category.
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES = [
    ("Food", "Words", "food", "fa-burger", 1),
    ("Groceries", "Words", "grocer,household,retail", "fa-cart-shopping", 2),
    ("Drinks", "Words", "drink,beverage,juice,soda", "fa-glass-water", 3),
    ("Snacks", "Words", "snack", "fa-cookie", 4),
    ("Bakery", "Words", "baker,bread,pastry,cake", "fa-bread-slice", 5),
    ("Offers", "Offers", "", "fa-tag", 6),
]


DELIVERY_DOCTYPE_MODULES = {
    # doctype -> expected module (the orphan-doctype pass deletes any doctype
    # whose controller import fails; a stale module field from a crashed sync
    # would make it delete ours - repair the linkage after every migrate)
    "DL Item Category": "Delivery Logistics",
    "DL Menu Item": "Delivery Logistics",
    "Delivery Order": "Delivery Logistics",
    "Delivery Order Item": "Delivery Logistics",
    "Parcel Request": "Delivery Logistics",
    "Transport Request": "Delivery Logistics",
    "Merchant": "Delivery Logistics",
    "Delivery Driver": "Delivery Logistics",
    "Logistics Settings": "Delivery Logistics",
    "Delivery Zone": "Delivery Logistics",
}


def repair_doctype_module_links():
    try:
        fixed = []
        for dt, expected in DELIVERY_DOCTYPE_MODULES.items():
            try:
                module = frappe.db.get_value("DocType", dt, "module")
            except Exception:
                continue
            if module and module != expected:
                frappe.db.set_value("DocType", dt, "module", expected)
                fixed.append("{0}: {1} -> {2}".format(dt, module, expected))
        if fixed:
            frappe.db.commit()
        return {"fixed": fixed}
    except Exception as e:
        frappe.log_error("Doctype module repair failed: {0}".format(e))
        return {"fixed": [], "error": str(e)}


def ensure_default_item_categories():
    """Seed the home-page categories once. Never allowed to break a migrate:
    guarded + fully wrapped - a seeding problem is logged, not fatal."""
    try:
        if not frappe.db.exists("DocType", "DL Item Category"):
            print("DL Item Category missing - skipping category seeding")
            return {"seeded": 0}
        if frappe.db.count("DL Item Category"):
            return {"seeded": 0}
        for name, mt, mv, icon, order in DEFAULT_CATEGORIES:
            if not frappe.db.exists("DL Item Category", name):
                frappe.get_doc({
                    "doctype": "DL Item Category",
                    "category_name": name,
                    "match_type": mt,
                    "match_value": mv,
                    "fontawesome_icon": icon,
                    "display_order": order,
                    "is_active": 1,
                }).insert(ignore_permissions=True)
        frappe.db.commit()
        return {"seeded": len(DEFAULT_CATEGORIES)}
    except Exception as e:
        frappe.log_error("Category seeding failed: {0}".format(e))
        print("Category seeding skipped:", e)
        return {"seeded": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Desk cleanup: show ONLY the Delivery app on the Desk home.
# The client does not use the stock ERPNext/Frappe modules, so their
# workspaces are hidden (not deleted) and a single public "Delivery"
# workspace takes the home screen. Fully reversible via desk_show_all().
# ---------------------------------------------------------------------------

DELIVERY_WS = "Delivery"

_WS_SHORTCUTS = [
    # client-approved order (top of Desk grid first)
    ("Delivery Orders", "Delivery Order"),
    ("Menu Items", "DL Menu Item"),
    ("Item Categories", "DL Item Category"),
    ("Merchants", "Merchant"),
    ("Drivers", "Delivery Driver"),
    ("Parcels", "Parcel Request"),
    ("Transport Trips", "Transport Request"),
    ("Home Banners", "Home Banner"),
    ("Reports", "page:delivery-reports"),
    ("Logistics Settings", "Logistics Settings"),
]


def _ws_block(btype, **data):
    return {"id": uuid.uuid4().hex[:10], "type": btype, "data": data}


def _ws_shortcut_row(label, target):
    if target.startswith("page:"):
        meta = frappe.get_meta("Workspace Shortcut")
        field = meta.get_field("type")
        opts = [o for o in (field.options or "").split("\n") if o] if field else []
        if opts and "Page" not in opts:
            # this build's Workspace Shortcut does not support Page tiles -
            # skip rather than crash the whole workspace sync (recovered next
            # migrate after an app update that adds support)
            print("Skipping Desk shortcut {0}: Page type not supported".format(label))
            return None
        return {"label": label, "type": "Page", "link_to": target[5:]}
    return {"label": label, "type": "DocType", "link_to": target, "doc_view": "List"}


def _workspace_content():
    blocks = [
        _ws_block("header", col=12,
                  text='<span class="h4"><b>Delivery &amp; Logistics</b></span>'),
        _ws_block("paragraph", col=12,
                  text="Run the whole delivery operation: orders, parcels, transport, "
                       "merchants and drivers. The customer shop itself lives at /delivery."),
    ]
    for label, _link_to in _WS_SHORTCUTS:
        blocks.append(_ws_block("shortcut", col=3, shortcut_name=label))
    return json.dumps(blocks)


def _ensure_delivery_workspace():
    """Create the public Delivery workspace, or SYNC an existing one to the
    current definition (shortcut order/list can change between releases -
    existing sites must pick the new layout up on the next migrate/run)."""
    if frappe.db.exists("Workspace", DELIVERY_WS):
        ws = frappe.get_doc("Workspace", DELIVERY_WS)
        ws.public = 1
        ws.is_hidden = 0
        ws.set("shortcuts", [])
        for label, link_to in _WS_SHORTCUTS:
            row = _ws_shortcut_row(label, link_to)
            if row:
                ws.append("shortcuts", row)
        ws.content = _workspace_content()
        ws.flags.ignore_permissions = True
        ws.save(ignore_permissions=True)
        return

    ws = frappe.new_doc("Workspace")
    ws.label = DELIVERY_WS
    ws.title = "Delivery"
    ws.type = "Workspace"
    ws.icon = "tool"
    ws.indicator_color = "purple"
    ws.module = "Delivery Logistics"
    ws.app = "delivery"
    ws.sequence_id = 1
    ws.public = 1
    ws.content = _workspace_content()

    for label, link_to in _WS_SHORTCUTS:
        row = _ws_shortcut_row(label, link_to)
        if row:
            ws.append("shortcuts", row)
    ws.append("links", {"type": "Card Break", "label": "Deliveries", "icon": "tool"})
    for label, link_to in _WS_SHORTCUTS[:5]:
        ws.append("links", {"type": "Link", "label": label,
                            "link_type": "DocType", "link_to": link_to})

    ws.insert(ignore_permissions=True)
    # belt & braces: make sure public sticks regardless of form-level defaults
    frappe.db.set_value("Workspace", DELIVERY_WS, "public", 1, update_modified=False)


def _ensure_delivery_desktop_icon():
    """Create the 'Delivery' desktop-grid icon (plain ORM, no frappe helper
    imports - helper names differ across v16 builds). Also create the
    matching Workspace Sidebar entry when that doctype exists, so the icon
    passes its boot-time permission check."""
    if frappe.db.exists("DocType", "Workspace Sidebar") \
            and not frappe.db.exists("Workspace Sidebar", DELIVERY_WS):
        try:
            sb = frappe.new_doc("Workspace Sidebar")
            sb.title = DELIVERY_WS
            sb.append("items", {"label": DELIVERY_WS, "type": "Link",
                                "link_to": DELIVERY_WS, "link_type": "Workspace"})
            sb.insert(ignore_permissions=True)
        except Exception:
            pass

    if frappe.db.exists("Desktop Icon", {"label": DELIVERY_WS}):
        frappe.db.set_value("Desktop Icon", {"label": DELIVERY_WS},
                            {"standard": 1, "idx": 0}, update_modified=False)
        return
    icon = frappe.new_doc("Desktop Icon")
    icon.label = DELIVERY_WS
    icon.icon_type = "Link"
    icon.link_type = "Workspace Sidebar"
    icon.link_to = DELIVERY_WS
    icon.icon = "tool"
    icon.standard = 1
    icon.idx = 0
    icon.insert(ignore_permissions=True)


def desk_show_delivery_only():
    """Desk home shows the Delivery app only.

    1. Ensure the public Delivery workspace exists.
    2. Hide other public workspaces (public=0, is_hidden=1 - nothing deleted).
    3. Prune the Desktop Icon grid FIRST: delete every STANDARD icon that is
       not the Delivery one (the v16 grid renders these records directly;
       stock tiles are baked in at install time and ignore workspace
       visibility). Delivery's own icon is created last and best-effort.
    Idempotent; re-runs automatically after every migrate (hooks.py).
    """
    ws_error = None
    try:
        _ensure_delivery_workspace()
    except Exception as e:
        # never let a workspace-sync problem skip the hiding/pruning below -
        # that is what re-establishes "Delivery only" after every migrate
        ws_error = str(e)
        frappe.log_error("Delivery workspace sync failed: {0}".format(ws_error))
    hidden = []
    for name in frappe.get_all("Workspace", filters={"public": 1}, pluck="name"):
        if name == DELIVERY_WS:
            continue
        frappe.db.set_value("Workspace", name,
                            {"public": 0, "is_hidden": 1}, update_modified=False)
        hidden.append(name)

    removed = []
    for row in frappe.get_all("Desktop Icon",
                              filters={"standard": 1},
                              fields=["name", "label"]):
        if row.label == DELIVERY_WS:
            continue
        try:
            frappe.delete_doc("Desktop Icon", row.name,
                              ignore_permissions=True, force=True)
            removed.append(row.label)
        except Exception:
            # last resort: hide it instead of deleting
            frappe.db.set_value("Desktop Icon", row.name, "hidden", 1,
                                update_modified=False)

    icon_error = None
    try:
        _ensure_delivery_desktop_icon()
    except Exception as e:
        icon_error = str(e)

    frappe.db.commit()
    _clear_desk_caches()
    result = {"kept_public": [DELIVERY_WS],
              "hidden_count": len(hidden), "hidden": hidden,
              "icons_removed": len(removed), "icons": removed}
    if icon_error:
        result["icon_warning"] = "Delivery tile could not be created: " + icon_error
    if ws_error:
        result["workspace_warning"] = ws_error
    return result


def _clear_desk_caches():
    """Desktop icons / bootinfo are cached aggressively; nuke all layers."""
    try:
        frappe.cache.delete_key("desktop_icons")
        frappe.cache.delete_key("bootinfo")
        from frappe.desk.doctype.desktop_icon import clear_desktop_icons_cache
        clear_desktop_icons_cache()
    except Exception:
        pass
    try:
        frappe.clear_cache()
    except Exception:
        pass


def desk_show_all():
    """Undo desk_show_delivery_only: restore the standard Frappe/ERPNext
    workspaces to public again and rebuild the default desktop icons."""
    restored = []
    for row in frappe.get_all("Workspace", filters={"public": 0, "is_hidden": 1},
                              fields=["name", "app"]):
        if row.name == DELIVERY_WS or (row.app or "") not in ("frappe", "erpnext"):
            continue
        frappe.db.set_value("Workspace", row.name,
                            {"public": 1, "is_hidden": 0}, update_modified=False)
        restored.append(row.name)

    try:
        from frappe.desk.doctype.desktop_icon import create_desktop_icons
        create_desktop_icons()
    except Exception:
        pass

    frappe.db.commit()
    _clear_desk_caches()
    return {"restored_count": len(restored), "restored": restored}


def link_merchant_user(merchant=None, user=None):
    """Link a Merchant record to a login so that user can use the merchant
    portal / Desk merchant features. If merchant is omitted, the user is
    linked to the only existing Merchant (or you are asked to specify).

        bench --site <s> execute delivery.maintenance.link_merchant_user \
            --kwargs '{"user": "merchant3@demo.com"}'
    """
    if not user:
        frappe.throw("Pass the login: --kwargs '{{\"user\": \"merchant3@demo.com\"}}'")
    if not frappe.db.exists("User", user):
        frappe.throw("No such User: {0}".format(user))
    if merchant:
        if not frappe.db.exists("Merchant", merchant):
            frappe.throw("No such Merchant: {0}".format(merchant))
    else:
        unlinked = frappe.get_all("Merchant",
                                  filters=[["portal_user", "in", ("", None)]],
                                  pluck="name")
        if len(unlinked) == 1:
            merchant = unlinked[0]
        else:
            frappe.throw("Pass the merchant too: --kwargs "
                         "'{{\"merchant\": \"MERCHANT-NAME\", \"user\": \"...\"}}' "
                         "(candidates: {0})".format(", ".join(unlinked)))
    frappe.db.set_value("Merchant", merchant, "portal_user", user,
                        update_modified=False)
    frappe.db.commit()
    try:
        frappe.clear_cache()
    except Exception:
        pass
    return {"merchant": merchant, "portal_user": user}


def ensure_merchant_user(email, merchant=None, password=None, first_name=None):
    """One-step merchant onboarding: creates the User if missing, grants the
    Merchant User role, links the Merchant record and (optionally) sets the
    login password.

        bench --site <s> execute delivery.maintenance.ensure_merchant_user \
            --kwargs '{"email": "merchant3@demo.com", "password": "merchant123"}'
    """
    from frappe.utils.password import update_password

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        frappe.throw("Pass a valid email: --kwargs '{{\"email\": \"...\", "
                     "\"password\": \"...\"}}'")

    if frappe.db.exists("User", email):
        user_doc = frappe.get_doc("User", email)
        # Desk access is required for the merchant Desk features; demo seeds
        # create merchants as "Website User", which is hard-blocked from Desk.
        if user_doc.user_type != "System User":
            user_doc.user_type = "System User"
            user_doc.save(ignore_permissions=True)
    else:
        user_doc = frappe.new_doc("User")
        user_doc.email = email
        user_doc.first_name = first_name or email.split("@")[0].title()
        user_doc.user_type = "System User"          # needs Desk access
        user_doc.send_welcome_email = 0
        user_doc.insert(ignore_permissions=True)

    if "Merchant User" not in frappe.get_roles(email):
        user_doc.add_roles("Merchant User")

    # resolve the merchant record:
    #   explicit argument > already linked to this login > the only unlinked one
    if merchant:
        if not frappe.db.exists("Merchant", merchant):
            frappe.throw("No such Merchant: {0}".format(merchant))
    else:
        linked = frappe.get_all("Merchant", filters={"portal_user": email},
                                pluck="name")
        if linked:
            merchant = linked[0]
        else:
            unlinked = frappe.get_all("Merchant",
                                      filters=[["portal_user", "in", ("", None)]],
                                      pluck="name")
            if len(unlinked) == 1:
                merchant = unlinked[0]
            else:
                frappe.throw("Pass the merchant too: --kwargs "
                             "'{{\"email\": \"...\", \"merchant\": \"MERCHANT-NAME\"}}' "
                             "(candidates: {0})".format(", ".join(unlinked) or "none"))

    frappe.db.set_value("Merchant", merchant, "portal_user", email,
                        update_modified=False)
    if password:
        update_password(email, password)

    frappe.db.commit()
    try:
        frappe.clear_cache()
    except Exception:
        pass
    return {"user": email, "merchant": merchant,
            "role": "Merchant User", "password_set": bool(password),
            "created_new_user": user_doc.is_new() if hasattr(user_doc, "is_new") else "linked"}


def list_merchant_logins():
    """Show every Merchant and which login (if any) can operate it."""
    out = []
    for m in frappe.get_all("Merchant",
                            fields=["name", "merchant_name", "portal_user"]):
        out.append({"merchant": m.name, "merchant_name": m.merchant_name,
                    "login": m.portal_user or "NOT LINKED"})
    return out


def ensure_driver_user(email, password=None, driver=None, first_name=None,
                       vehicle_type="Car", max_load_kg=300, phone=None):
    """One-step driver onboarding: creates/updates the User (Driver role +
    Desk access), creates or links the Delivery Driver record.

        bench --site <s> execute delivery.maintenance.ensure_driver_user \
            --kwargs '{"email": "driver@yourdomain.tz", "password": "..."}'
    """
    from frappe.utils.password import update_password

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        frappe.throw("Pass a valid email: --kwargs '{{\"email\": \"...\", "
                     "\"password\": \"...\"}}'")

    if frappe.db.exists("User", email):
        user_doc = frappe.get_doc("User", email)
        if user_doc.user_type != "System User":
            user_doc.user_type = "System User"
            user_doc.save(ignore_permissions=True)
    else:
        user_doc = frappe.new_doc("User")
        user_doc.email = email
        user_doc.first_name = first_name or email.split("@")[0].title()
        user_doc.user_type = "System User"
        user_doc.send_welcome_email = 0
        user_doc.insert(ignore_permissions=True)

    if "Driver" not in frappe.get_roles(email):
        user_doc.add_roles("Driver")

    # resolve the Delivery Driver record: explicit > linked > create new
    if driver:
        if not frappe.db.exists("Delivery Driver", driver):
            frappe.throw("No such Delivery Driver: {0}".format(driver))
    else:
        linked = frappe.get_all("Delivery Driver", filters={"user": email},
                                pluck="name")
        if linked:
            driver = linked[0]
        else:
            n = frappe.db.count("Delivery Driver") + 1
            code = "DR-{0:03d}".format(n)
            while frappe.db.exists("Delivery Driver", code):
                n += 1
                code = "DR-{0:03d}".format(n)
            rec = frappe.new_doc("Delivery Driver")
            rec.driver_code = code
            rec.driver_name = first_name or email.split("@")[0].title()
            rec.user = email
            rec.vehicle_type = vehicle_type
            rec.max_load_kg = max_load_kg
            if phone:
                rec.phone = phone
            rec.insert(ignore_permissions=True)
            driver = rec.name

    frappe.db.set_value("Delivery Driver", driver, "user", email,
                        update_modified=False)
    if password:
        update_password(email, password)

    frappe.db.commit()
    try:
        frappe.clear_cache()
    except Exception:
        pass
    return {"user": email, "driver": driver, "role": "Driver",
            "password_set": bool(password)}


def list_driver_logins():
    """Show every Delivery Driver and which login (if any) operates it."""
    return [{"driver": d.name, "driver_name": d.driver_name,
             "login": d.user or "NOT LINKED"}
            for d in frappe.get_all("Delivery Driver",
                                    fields=["name", "driver_name", "user"])]
