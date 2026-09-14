"""
Row-level security for the web portal.

Portal roles may only reach the documents that belong to them:

* Delivery Customer  -> own service documents only
* Merchant User      -> Delivery Orders placed against their merchant
* Driver             -> jobs assigned to them
* Delivery Operations / System Manager -> everything

Falls back to Frappe's own permission check for desk users.
"""
import frappe


def _roles():
    return frappe.get_roles()


def _is_ops():
    return bool({"System Manager", "Delivery Operations"} & set(_roles()))


def _my_merchants(user=None):
    return frappe.get_all("Merchant", filters={"portal_user": user or frappe.session.user},
                          pluck="name") or []


def _my_driver_codes(user=None):
    return frappe.get_all("Delivery Driver", filters={"user": user or frappe.session.user},
                          pluck="name") or []


def _owner_check(doc, user_field="customer"):
    if _is_ops():
        return True
    if frappe.session.user == "Administrator":
        return True
    if getattr(doc, user_field, None) == frappe.session.user:
        return True
    return False


def order_permission(doc, user=None, permission_type=None):
    """Delivery Order: customer / merchant / driver / ops."""
    if _is_ops():
        return True
    user = user or frappe.session.user
    if doc.get("customer") == user:
        return True
    if "Merchant User" in _roles() and doc.get("merchant") in _my_merchants():
        return True
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_codes():
        return True
    return False


def parcel_permission(doc, user=None, permission_type=None):
    if _is_ops():
        return True
    user = user or frappe.session.user
    if doc.get("customer") == user:
        return True
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_codes():
        return True
    return False


def transport_permission(doc, user=None, permission_type=None):
    if _is_ops():
        return True
    user = user or frappe.session.user
    if doc.get("customer") == user:
        return True
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_codes():
        return True
    return False


def payment_permission(doc, user=None, permission_type=None):
    if _is_ops():
        return True
    user = user or frappe.session.user
    if not doc.get("reference_doctype") or not doc.get("reference_name"):
        return False
    try:
        src = frappe.get_doc(doc.reference_doctype, doc.reference_name)
    except frappe.DoesNotExistError:
        return False
    check = {
        "Delivery Order": order_permission,
        "Parcel Request": parcel_permission,
        "Transport Request": transport_permission,
    }.get(doc.reference_doctype)
    return bool(check and check(src, user))


# ---------------------------------------------------------------------------
# Desk list-view scoping (permission_query_conditions hooks).
# has_permission only guards opening one document; WITHOUT these conditions
# the Desk LIST shows every merchant's records. Wire-up lives in hooks.py.
# ---------------------------------------------------------------------------

def _unrestricted(user):
    if not user or user == "Administrator":
        return True
    return bool({"System Manager", "Delivery Operations"} & set(frappe.get_roles(user)))


def _in_sql(field, values):
    vals = ", ".join(frappe.db.escape(v) for v in values)
    return f"{field} in ({vals})"


def _scoped_conditions(user, doctype, clauses):
    """clauses: list of raw SQL fragments (OR-ed). None = no restriction."""
    if _unrestricted(user):
        return None
    parts = []
    if "Merchant User" in frappe.get_roles(user):
        merchants = _my_merchants(user)
        if merchants:
            parts.append(_in_sql(f"`tab{doctype}`.`merchant`", merchants))
    if doctype == "Delivery Order":
        drivers = _my_driver_codes(user)
        if drivers:
            parts.append(_in_sql(f"`tab{doctype}`.`assigned_driver`", drivers))
        parts.append(f"`tab{doctype}`.`customer` = {frappe.db.escape(user)}")
    if not parts:
        return "1=0"
    return "(" + " or ".join(parts) + ")"


def order_query_conditions(user=None, doctype=None):
    return _scoped_conditions(user or frappe.session.user, "Delivery Order", [])


def menu_item_query_conditions(user=None, doctype=None):
    """Merchants see only their own menu items in Desk; ops/admin see all."""
    user = user or frappe.session.user
    if _unrestricted(user):
        return None
    merchants = _my_merchants(user)
    if not merchants:
        return "1=0"
    return _in_sql("`tabDL Menu Item`.`merchant`", merchants)


def parcel_query_conditions(user=None, doctype=None):
    """Desk: customers see own parcels; drivers assigned ones; merchants none."""
    user = user or frappe.session.user
    if _unrestricted(user):
        return None
    parts = [f"`tabParcel Request`.`customer` = {frappe.db.escape(user)}"]
    drivers = _my_driver_codes(user)
    if drivers:
        parts.append(_in_sql("`tabParcel Request`.`assigned_driver`", drivers))
    return "(" + " or ".join(parts) + ")"


def transport_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if _unrestricted(user):
        return None
    parts = [f"`tabTransport Request`.`customer` = {frappe.db.escape(user)}"]
    drivers = _my_driver_codes(user)
    if drivers:
        parts.append(_in_sql("`tabTransport Request`.`assigned_driver`", drivers))
    return "(" + " or ".join(parts) + ")"


def menu_item_permission(doc, user=None, permission_type=None):
    """DL Menu Item: merchants may only read/write their own items;
    ops/admin unrestricted. (DocType perms already exclude other roles.)"""
    user = user or frappe.session.user
    if _unrestricted(user):
        return True
    if "Merchant User" in frappe.get_roles(user):
        return doc.get("merchant") in _my_merchants(user)
    return False
