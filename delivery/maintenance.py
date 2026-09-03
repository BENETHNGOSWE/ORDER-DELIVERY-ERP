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
