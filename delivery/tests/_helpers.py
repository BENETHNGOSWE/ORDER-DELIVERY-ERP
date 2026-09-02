"""Shared test helpers."""
import frappe

PASSWORD = "Sw!ftLog1stics26"


class _Fake:
    """
    Minimal stand-in for a Frappe Document.

    ``state_machine`` only needs ``doctype``, ``name``, ``get()``, attribute
    read/write and ``add_comment()``, so the state matrix can be tested without
    touching the database.
    """

    def __init__(self, doctype="Delivery Order", name="TEST-0001", **kw):
        object.__setattr__(self, "_data", {"workflow_state": None,
                                           "order_type": "Food"})
        object.__setattr__(self, "doctype", doctype)
        object.__setattr__(self, "name", name)
        self._data.update(kw)

    # dict-ish access -------------------------------------------------
    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def add_comment(self, *args, **kwargs):
        return None

    def save(self, *args, **kwargs):
        return self

    # attribute access ------------------------------------------------
    def __getattr__(self, key):
        data = object.__getattribute__(self, "_data")
        if key in data:
            return data[key]
        raise AttributeError(key)

    def __setattr__(self, key, value):
        if key.startswith("_") or key in ("doctype", "name"):
            object.__setattr__(self, key, value)
        else:
            self._data[key] = value


def _merchant(service_type="Food", user=None):
    """A merchant whose portal_user is ``user`` (defaults to the test login)."""
    filters = {"service_type": ["in", [service_type, "Food & Retail"]]}
    if user:
        filters["portal_user"] = user
    name = frappe.db.get_value("Merchant", filters, "name",
                               order_by="merchant_name asc")
    if not name:
        frappe.throw("No demo merchant of type {0}".format(service_type))
    return name


def _item(merchant, n=2):
    return frappe.get_all("DL Menu Item",
                          filters={"merchant": merchant, "published": 1},
                          fields=["name", "standard_rate"],
                          order_by="item_name asc", limit=n)


def _driver_for(login, capability="can_food"):
    """A driver record whose user is ``login`` and who has the capability."""
    code = frappe.db.get_value("Delivery Driver",
                               {"user": login, capability: 1}, "name")
    if not code:
        frappe.throw("No demo driver for {0} with {1}".format(login, capability))
    return code
