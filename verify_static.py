#!/usr/bin/env python3
"""
Static verification for the delivery app.

The sandbox lost its database and Python environment, so the runtime suites
cannot execute here. This script verifies everything that can be checked without
a live Frappe site - most importantly the class of bug that produced a real
HTTP 500 earlier: Python asking for a field the DocType does not define.

Run:  python3 /home/user/verify_static.py
Exit 0 = all checks pass.
"""
import ast
import json
import os
import re
import sys

APP = os.environ.get("DELIVERY_APP") or os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(APP, "delivery")
DT_DIR = os.path.join(PKG, "delivery_logistics", "doctype")

PASS, FAIL = 0, 0
FAILURES = []


def check(ok, label, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  {0}{1}".format(label, ("   [" + str(detail) + "]") if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(label)
        print("  FAIL  {0}{1}".format(label, ("   [" + str(detail) + "]") if detail else ""))


def section(title):
    print("\n" + title)
    print("-" * len(title))


# ---------------------------------------------------------------------------
def load_doctypes():
    schema = {}
    for name in sorted(os.listdir(DT_DIR)):
        path = os.path.join(DT_DIR, name, name + ".json")
        if not os.path.isfile(path):
            continue
        with open(path) as fh:
            doc = json.load(fh)
        schema[doc["name"]] = doc
    return schema


SCHEMA = load_doctypes()
FIELDS = {dt: {f["fieldname"] for f in doc["fields"]} for dt, doc in SCHEMA.items()}
# fields Frappe adds to every table
IMPLICIT = {"name", "owner", "creation", "modified", "modified_by", "docstatus",
            "parent", "parentfield", "parenttype", "idx", "doctype"}


# ---------------------------------------------------------------------------
def check_python_compiles():
    section("[1] Python modules compile")
    bad = []
    count = 0
    for root, _dirs, files in os.walk(PKG):
        for f in files:
            if not f.endswith(".py"):
                continue
            count += 1
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    compile(fh.read(), path, "exec")
            except SyntaxError as exc:
                bad.append("{0}: {1}".format(path, exc))
    check(not bad, "{0} modules compile".format(count),
          "; ".join(bad) if bad else "")


def check_doctype_json():
    section("[2] DocType definitions")
    required = {"name", "module", "fields", "doctype"}
    check(len(SCHEMA) == 14, "14 doctypes defined", len(SCHEMA))

    bad = []
    for dt, doc in SCHEMA.items():
        missing = required - set(doc)
        if missing:
            bad.append("{0} missing {1}".format(dt, sorted(missing)))
        if doc["module"] != "Delivery Logistics":
            bad.append("{0} in wrong module {1}".format(dt, doc["module"]))
        if not doc["fields"]:
            bad.append("{0} has no fields".format(dt))
        if doc.get("istable") and not any(f["fieldname"] == "parent"
                                          for f in doc["fields"]):
            pass  # child tables get parent implicitly
    check(not bad, "every doctype is well formed", "; ".join(bad) if bad else "")

    # child tables must be declared istable
    children = {"Delivery Order Item", "Transport Stop", "Dispatch Trip Stop"}
    bad = [dt for dt in children if not SCHEMA[dt].get("istable")]
    check(not bad, "child tables declared istable", ", ".join(bad) or "")

    # every Table field must point at a real child table
    bad = []
    for dt, doc in SCHEMA.items():
        for f in doc["fields"]:
            if f["fieldtype"] == "Table" and f.get("options") not in SCHEMA:
                bad.append("{0}.{1} -> {2}".format(dt, f["fieldname"], f.get("options")))
    check(not bad, "every Table field links a real child doctype",
          "; ".join(bad) or "")


def check_modules_txt():
    section("[3] Module wiring")
    path = os.path.join(PKG, "modules.txt")
    exists = os.path.isfile(path)
    check(exists, "modules.txt exists")
    if not exists:
        return
    content = open(path).read().strip()
    check(content == "Delivery Logistics", "modules.txt names the module exactly",
          repr(content))
    mod_dir = os.path.join(PKG, "delivery_logistics")
    check(os.path.isdir(mod_dir), "module directory exists (delivery_logistics)")
    check(os.path.isfile(os.path.join(mod_dir, "__init__.py")),
          "module has __init__.py")


# ---------------------------------------------------------------------------
def _str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def iter_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _callee(node):
    f = node.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def check_field_references():
    """
    The check that matters most: every field a Python module asks Frappe for
    must exist on the DocType it asks it from.

    A missing column is a MySQL 1054 at request time, not at import time, so it
    sails through py_compile and only surfaces in production.
    """
    section("[4] Field references resolve against the DocTypes")
    problems = []
    checked = 0

    for root, _dirs, files in os.walk(PKG):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, PKG)
            tree = ast.parse(open(path).read())

            for node in iter_calls(tree):
                callee = _callee(node)
                if callee not in ("frappe.get_all", "frappe.get_list",
                                  "frappe.db.get_value", "frappe.db.count",
                                  "frappe.db.set_value"):
                    continue
                if not node.args:
                    continue
                dt = _str(node.args[0])
                if not dt or dt not in FIELDS:
                    continue          # dynamic doctype - cannot check statically

                allowed = FIELDS[dt] | IMPLICIT

                if callee == "frappe.db.count":
                    continue

                # positional field(s) for db.get_value / db.set_value
                if callee == "frappe.db.get_value" and len(node.args) > 2:
                    for want in [_str(node.args[2])]:
                        if want and want != "*" and want not in allowed:
                            problems.append("{0}: {1}.{2}".format(rel, dt, want))
                        elif want:
                            checked += 1
                if callee == "frappe.db.set_value" and len(node.args) > 2:
                    want = _str(node.args[2])
                    if want and want not in allowed:
                        problems.append("{0}: {1}.{2}".format(rel, dt, want))
                    elif want:
                        checked += 1

                # keyword args: fields=[...], filters={...}, pluck=, order_by=
                for kw in node.keywords:
                    if kw.arg == "fields" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        for el in kw.value.elts:
                            want = _str(el)
                            if not want or want == "*":
                                continue
                            base = re.split(r"\s+as\s+", want)[0].split(".")[-1]
                            if "(" in base:
                                continue      # aggregate
                            if base not in allowed:
                                problems.append("{0}: {1}.{2}".format(rel, dt, base))
                            else:
                                checked += 1
                    elif kw.arg == "filters" and isinstance(kw.value, ast.Dict):
                        for k in kw.value.keys:
                            want = _str(k)
                            if want and want not in allowed:
                                problems.append("{0}: {1}.{2}".format(rel, dt, want))
                            elif want:
                                checked += 1
                    elif kw.arg in ("pluck", "order_by", "group_by"):
                        want = _str(kw.value)
                        if want:
                            for part in re.split(r"[,\s]+", want):
                                part = part.strip()
                                if not part or part in ("asc", "desc"):
                                    continue
                                part = part.split(".")[-1]
                                if part not in allowed:
                                    problems.append("{0}: {1}.{2}".format(rel, dt, part))
                                else:
                                    checked += 1

    # -- dynamically assembled field lists --------------------------------
    # driver.py builds its SELECT list from module-level maps rather than a
    # literal, which is exactly where the real "Unknown column pickup_address"
    # bug lived. Resolve those maps too.
    dyn_checked, dyn_problems = _check_field_maps()
    checked += dyn_checked
    problems += dyn_problems

    check(not problems,
          "{0} field references resolve".format(checked),
          "; ".join(sorted(set(problems))[:12]) if problems else "")


def _literal_strings(node):
    """All string constants in a literal expression (list/tuple/dict/str)."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def _check_field_maps():
    """
    Validate two shapes the literal scan cannot see:

    1. a dict literal keyed by DocType name whose values are field names
       (``ADDRESS_COLS = {"Delivery Order": ("pickup_address", ...)}``);
    2. a module-level list of field names passed as ``fields=`` to a query whose
       DocType is a literal (``_ORDER_FIELDS = [...]; get_all("Delivery Order",
       fields=_ORDER_FIELDS)``).
    """
    problems, checked = [], 0

    for root, _dirs, files in os.walk(PKG):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, PKG)
            tree = ast.parse(open(path).read())

            # (1) doctype-keyed field maps.
            # Scoped by assignment name: ADDRESS_COLS / AMOUNT_FIELD hold field
            # names, while SERVICE_LABEL holds display text, _CAPABILITY holds
            # fields of a *different* doctype (Delivery Driver), and
            # has_permission holds dotted import paths. Checking all of them
            # as field names produces false positives.
            field_maps = []
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = [t for t in node.targets if isinstance(t, ast.Name)]
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    targets = [node.target]
                for t in targets:
                    if re.search(r"_(COLS|COLUMNS|FIELDS?)$", t.id, re.I) \
                            and isinstance(node.value, ast.Dict):
                        field_maps.append((t.id, node.value))

            for map_name, node in field_maps:
                for key, value in zip(node.keys, node.values):
                    dt = _str(key)
                    if not dt or dt not in FIELDS:
                        continue
                    allowed = FIELDS[dt] | IMPLICIT
                    for want in _literal_strings(value):
                        if "(" in want or want == "*":
                            continue
                        if want not in allowed:
                            problems.append("{0}: {1}.{2} (in {3})".format(
                                rel, dt, want, map_name))
                        else:
                            checked += 1

            # (2) named field lists passed to a query with a literal doctype
            lists = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            lists[t.id] = _literal_strings(node.value)
            if not lists:
                continue
            for node in iter_calls(tree):
                if _callee(node) not in ("frappe.get_all", "frappe.get_list") or not node.args:
                    continue
                dt = _str(node.args[0])
                if not dt or dt not in FIELDS:
                    continue
                allowed = FIELDS[dt] | IMPLICIT
                for kw in node.keywords:
                    if kw.arg == "fields" and isinstance(kw.value, ast.Name):
                        for want in lists.get(kw.value.id, []):
                            if "(" in want or want == "*":
                                continue
                            if want not in allowed:
                                problems.append("{0}: {1}.{2} (via {3})".format(
                                    rel, dt, want, kw.value.id))
                            else:
                                checked += 1

    return checked, problems


# ---------------------------------------------------------------------------
def whitelisted_functions():
    """Map dotted path -> True for every @frappe.whitelist function."""
    out = {}
    for root, _dirs, files in os.walk(PKG):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, PKG).replace(os.sep, ".")[:-3]
            module = "delivery." + rel
            tree = ast.parse(open(path).read())
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list:
                        target = dec.func if isinstance(dec, ast.Call) else dec
                        name = _callee_from(target)
                        if name in ("frappe.whitelist", "whitelist"):
                            out["{0}.{1}".format(module, node.name)] = True
    return out


def _callee_from(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def check_api_surface():
    section("[5] Every API the portal calls exists and is whitelisted")
    known = whitelisted_functions()

    wanted = set()
    pattern = re.compile(r"delivery\.(?:api|portal)\.[a-z_]+\.[a-z_]+")
    for root, _dirs, files in os.walk(PKG):
        for f in files:
            if not f.endswith((".html", ".js", ".py")):
                continue
            text = open(os.path.join(root, f)).read()
            wanted.update(pattern.findall(text))

    missing = sorted(w for w in wanted if w not in known)
    check(bool(known), "{0} whitelisted endpoints found".format(len(known)))
    check(not missing, "{0} referenced endpoints all resolve".format(len(wanted)),
          ", ".join(missing) if missing else "")

    # the modules hooks.py points at must exist
    hooks = open(os.path.join(PKG, "hooks.py")).read()
    for dotted in re.findall(r'"(delivery\.[a-z_.]+)"', hooks):
        module, _, attr = dotted.rpartition(".")
        path = os.path.join(PKG, *module.split(".")[1:]) + ".py"
        if not os.path.isfile(path):
            path = os.path.join(PKG, *module.split(".")[1:], "__init__.py")
        ok = os.path.isfile(path)
        if ok:
            ok = attr in open(path).read()
        check(ok, "hooks reference resolves: {0}".format(dotted))


# ---------------------------------------------------------------------------
def check_templates():
    section("[6] Portal templates")
    www = os.path.join(PKG, "www", "delivery")
    pages = sorted(f for f in os.listdir(www) if f.endswith(".html")) if os.path.isdir(www) else []
    check(len(pages) == 10, "10 portal pages present", ", ".join(pages))

    bad = []
    for f in pages:
        text = open(os.path.join(www, f)).read()
        for inc in re.findall(r'{%\s*include\s+"([^"]+)"', text):
            path = os.path.join(APP, *inc.split("/"))
            if not os.path.isfile(path):
                bad.append("{0} -> {1}".format(f, inc))
    check(not bad, "every Jinja include resolves", "; ".join(bad) or "")

    bad = []
    for f in pages:
        text = open(os.path.join(www, f)).read()
        for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', text):
            path = os.path.join(PKG, "public", *asset.split("/assets/delivery/")[1].split("/"))
            if not os.path.isfile(path):
                bad.append("{0} -> {1}".format(f, asset))
    check(not bad, "every asset path resolves", "; ".join(bad) or "")

    # no page may extend a template (would inherit the site theme) and none may
    # rely on a global include hook
    bad = [f for f in pages if "{% extends" in open(os.path.join(www, f)).read()]
    check(not bad, "pages are standalone (no theme coupling)", ", ".join(bad) or "")


def check_public_assets():
    section("[7] Public assets")
    js = os.path.join(PKG, "public", "js", "delivery_portal.js")
    css = os.path.join(PKG, "public", "css", "delivery_portal.css")
    check(os.path.isfile(js), "portal JS present",
          "{0} bytes".format(os.path.getsize(js)) if os.path.isfile(js) else "")
    check(os.path.isfile(css), "portal CSS present",
          "{0} bytes".format(os.path.getsize(css)) if os.path.isfile(css) else "")


def _hooks_assignments():
    """Module-level names actually assigned in hooks.py (comments ignored)."""
    tree = ast.parse(open(os.path.join(PKG, "hooks.py")).read())
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names[node.target.id] = node.value
    return names


def check_no_site_coupling():
    """
    Dropping this app onto a live site must not change how that site behaves.

    Checked against the parsed AST, not the file text - hooks.py documents why
    each of these is deliberately absent, and a substring search would flag the
    explanation itself.
    """
    section("[8] Production safety")
    assigned = _hooks_assignments()

    check("base_template" not in assigned,
          "no base_template (would restyle the whole site incl. desk)")
    check("website_redirects" not in assigned,
          "no website_redirects (would hijack the site homepage)")
    check("web_include_js" not in assigned and "web_include_css" not in assigned,
          "no global web_include_js/css (assets are page-scoped)")

    doc_events = assigned.get("doc_events")
    check(isinstance(doc_events, ast.Dict) and not doc_events.keys,
          "doc_events empty (avoids a doubled validate pass)",
          "{0} entries".format(len(doc_events.keys)) if isinstance(doc_events, ast.Dict) else "?")

    # the sandbox site name must not be baked in anywhere
    leaked = []
    for root, _dirs, files in os.walk(PKG):
        for f in files:
            if not f.endswith((".py", ".json", ".html", ".js")):
                continue
            path = os.path.join(root, f)
            try:
                tree = ast.parse(open(path).read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # word-bounded so the demo app_email "ops@swiftlogistics.test"
                    # (a different domain) is not mistaken for the sandbox site
                    if re.search(r"(?<![a-z0-9.])logistics\.test(?![a-z])", node.value):
                        leaked.append("{0}: {1!r}".format(
                            os.path.relpath(path, PKG), node.value))
    check(not leaked, "no sandbox site name baked into the app",
          "; ".join(leaked) or "")

    # website_user_home_page must return "" for non-delivery users
    portal = open(os.path.join(PKG, "portal.py")).read()
    check('return ""' in portal,
          "portal home-page hook falls through for non-delivery users")

    stale = []
    for root, _dirs, files in os.walk(PKG):
        for f in files:
            if not f.endswith((".py", ".json", ".html")):
                continue
            p = os.path.join(root, f)
            text = open(p, errors="ignore").read()
            for token in ("Delivery Settings", "tabDelivery Settings"):
                if token in text:
                    stale.append("{0}: {1}".format(os.path.relpath(p, PKG), token))
    check(not stale, "no references to the renamed 'Delivery Settings'",
          "; ".join(stale) or "")

    check(not os.path.isdir(os.path.join(DT_DIR, "delivery_settings")),
          "stale delivery_settings doctype removed")
    check(not os.path.isdir(os.path.join(DT_DIR, "delivery_trip")),
          "stale delivery_trip doctype removed")


def check_required_files():
    section("[9] App skeleton")
    required = [
        "hooks.py", "install.py", "permissions.py", "portal.py", "tasks.py",
        "demo_data.py", "modules.txt", "__init__.py",
        "delivery_logistics/__init__.py",
        "delivery_logistics/state_machine.py",
        "delivery_logistics/billing.py",
        "delivery_logistics/payments.py",
        "delivery_logistics/base.py",
        "api/customer.py", "api/merchant.py", "api/operations.py", "api/driver.py",
        "locale/sw.csv",
        "tests/test_state_machine.py", "tests/test_billing.py",
        "tests/test_workflows.py",
    ]
    missing = [r for r in required if not os.path.isfile(os.path.join(PKG, r))]
    check(not missing, "all required modules present", ", ".join(missing) or "")

    pyproject = os.path.join(APP, "pyproject.toml")
    check(os.path.isfile(pyproject), "pyproject.toml present")


def main():
    print("=" * 72)
    print("DELIVERY APP - STATIC VERIFICATION")
    print("=" * 72)

    check_python_compiles()
    check_doctype_json()
    check_modules_txt()
    check_field_references()
    check_api_surface()
    check_templates()
    check_public_assets()
    check_no_site_coupling()
    check_required_files()

    print("\n" + "=" * 72)
    print("RESULT: {0} passed, {1} failed".format(PASS, FAIL))
    if FAILURES:
        print("Failed:")
        for f in FAILURES:
            print("  - " + f)
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
