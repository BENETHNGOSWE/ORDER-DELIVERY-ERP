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


def _my_merchants():
    return frappe.get_all("Merchant", filters={"portal_user": frappe.session.user},
                          pluck="name") or []


def _my_driver_code():
    return frappe.get_all("Delivery Driver", filters={"user": frappe.session.user},
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
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_code():
        return True
    return False


def parcel_permission(doc, user=None, permission_type=None):
    if _is_ops():
        return True
    user = user or frappe.session.user
    if doc.get("customer") == user:
        return True
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_code():
        return True
    return False


def transport_permission(doc, user=None, permission_type=None):
    if _is_ops():
        return True
    user = user or frappe.session.user
    if doc.get("customer") == user:
        return True
    if "Driver" in _roles() and doc.get("assigned_driver") in _my_driver_code():
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
