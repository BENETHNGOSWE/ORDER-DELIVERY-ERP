"""
Merchant Web Portal API - SRS section 2 (Merchant Web Portal).

Every call is scoped to the merchant record whose ``portal_user`` is the caller,
so one restaurant can never read or act on another's data.

Route prefix: /api/method/delivery.api.merchant.*
"""
import frappe
from frappe import _
from frappe.utils import flt


# ---------------------------------------------------------------------------
# scoping
# ---------------------------------------------------------------------------
def _require_login():
    if frappe.session.user in ("", "Guest"):
        frappe.throw(_("Please log in."), frappe.AuthenticationError)
    return frappe.session.user


def _my_merchants():
    _require_login()
    return frappe.get_all("Merchant", filters={"portal_user": frappe.session.user},
                          pluck="name") or []


def _merchant_or_throw(merchant=None):
    """Resolve the merchant this login manages, asserting ownership."""
    mine = _my_merchants()
    if not mine:
        frappe.throw(_("Your login is not linked to a merchant profile."),
                     frappe.PermissionError)

    if merchant:
        if merchant not in mine:
            frappe.throw(_("You do not manage {0}.").format(merchant),
                         frappe.PermissionError)
        return merchant

    if len(mine) > 1:
        frappe.throw(_("Specify which merchant: {0}.").format(", ".join(mine)),
                     title=_("Ambiguous Merchant"))
    return mine[0]


def _assert_mine(merchant):
    if merchant not in _my_merchants():
        frappe.throw(_("You do not manage {0}.").format(merchant),
                     frappe.PermissionError)
    return merchant


def _order(reference):
    order = frappe.get_doc("Delivery Order", reference)
    _assert_mine(order.merchant)
    return order


# ---------------------------------------------------------------------------
# identity / profile
# ---------------------------------------------------------------------------
@frappe.whitelist()
def whoami():
    mine = _my_merchants()
    if not mine:
        frappe.throw(_("Your login is not linked to a merchant profile."),
                     frappe.PermissionError)
    # ownership is asserted by _my_merchants(); read via db (no doctype read
    # permission - merchants intentionally cannot browse other merchants)
    m = frappe.db.get_value("Merchant", mine[0],
                            ["name", "merchant_name", "service_type", "status"],
                            as_dict=True)
    return {"user": frappe.session.user, "merchant": m.name,
            "merchant_name": m.merchant_name, "service_type": m.service_type,
            "status": m.status, "all": mine}


@frappe.whitelist()
def profile(merchant=None):
    name = _merchant_or_throw(merchant)
    m = frappe.db.get_value(
        "Merchant", name,
        ["name", "merchant_name", "service_type", "status", "phone", "email",
         "city", "area", "full_address", "avg_prep_minutes",
         "minimum_order_value", "delivery_radius_km", "commission_rate", "logo"],
        as_dict=True)
    return {"merchant": m.name, "merchant_name": m.merchant_name,
            "service_type": m.service_type, "status": m.status,
            "phone": m.phone, "email": m.email, "city": m.city, "area": m.area,
            "logo": m.logo or "",
            "full_address": m.full_address, "avg_prep_minutes": m.avg_prep_minutes,
            "minimum_order_value": flt(m.minimum_order_value, 2),
            "delivery_radius_km": flt(m.delivery_radius_km, 2),
            "commission_rate": flt(m.commission_rate, 2)}


@frappe.whitelist()
def set_logo(image_data=None, merchant=None):
    """Save an uploaded image as the merchant logo (shown on the customer
    restaurant list + homepage). Accepts a base64 data URL from the portal."""
    import base64
    name = _merchant_or_throw(merchant)
    if not image_data or "," not in image_data:
        frappe.throw(_("Please choose an image first."))
    head, b64 = image_data.split(",", 1)
    ext = "png" if "png" in head.lower() else "jpg"
    doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{name}-logo.{ext}",
        "attached_to_doctype": "Merchant",
        "attached_to_name": name,
        "is_private": 0,
        "content": base64.b64decode(b64),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.set_value("Merchant", name, "logo", doc.file_url)
    frappe.db.commit()
    return {"logo": doc.file_url}


@frappe.whitelist()
def set_open(is_open=1, merchant=None):
    name = _merchant_or_throw(merchant)
    status = "Open" if int(is_open) else "Closed"
    frappe.db.set_value("Merchant", name, "status", status)
    frappe.db.commit()
    return {"merchant": name, "status": status}


# ---------------------------------------------------------------------------
# catalogue (SRS 2 - Manage Menu/Inventory)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def catalog(merchant=None, published=None):
    name = _merchant_or_throw(merchant)
    filters = {"merchant": name}
    if published is not None:
        filters["published"] = int(published)
    return frappe.get_all("DL Menu Item", filters=filters,
                          fields=["name", "item_code", "item_name", "item_type",
                                  "category", "description", "standard_rate",
                                  "discount_rate", "available_stock", "track_stock",
                                  "prep_minutes", "published", "is_featured",
                                  "apply_service_charge", "service_charge_pct", "service_fee"],
                          order_by="category asc, item_name asc", limit=500)


@frappe.whitelist()
def add_item(merchant, item_name, item_type="Restaurant", category=None,
             standard_rate=0, description=None, prep_minutes=0,
             available_stock=0, track_stock=0, published=1, item_code=None,
             apply_service_charge=0, service_charge_pct=0, service_fee=0):
    _assert_mine(merchant)
    code = item_code or "{0}-{1}".format(
        merchant, frappe.scrub(item_name)[:24]).upper().replace(" ", "-")

    item = frappe.get_doc({
        "doctype": "DL Menu Item",
        "item_code": code,
        "item_name": item_name,
        "merchant": merchant,
        "item_type": item_type,
        "category": category or "General",
        "description": description,
        "standard_rate": flt(standard_rate),
        "prep_minutes": int(prep_minutes),
        "available_stock": int(available_stock),
        "track_stock": int(track_stock),
        "published": int(published),
        "apply_service_charge": int(apply_service_charge or 0),
        "service_charge_pct": (flt(service_charge_pct)
                               if int(apply_service_charge or 0) else 0),
        "service_fee": flt(service_fee or 0),
    })
    item.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"item": item.name, "item_code": item.item_code}


@frappe.whitelist()
def update_item(item, **changes):
    doc = frappe.get_doc("DL Menu Item", item)
    _assert_mine(doc.merchant)

    allowed = {"item_name", "category", "description", "standard_rate",
               "discount_rate", "prep_minutes", "published", "is_featured",
               "available_stock", "track_stock",
               "apply_service_charge", "service_charge_pct", "service_fee"}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key in ("standard_rate", "discount_rate", "service_charge_pct", "service_fee"):
            value = flt(value)
        elif key in ("prep_minutes", "available_stock", "apply_service_charge"):
            value = int(flt(value))
        elif key in ("published", "is_featured", "track_stock"):
            value = int(value)
        doc.set(key, value)

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"item": doc.name}


@frappe.whitelist()
def set_stock(item, qty):
    """SRS 2 - Real-time stock availability."""
    doc = frappe.get_doc("DL Menu Item", item)
    _assert_mine(doc.merchant)
    doc.available_stock = int(flt(qty))
    doc.track_stock = 1
    if doc.available_stock <= 0:
        doc.published = 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"item": doc.name, "available_stock": doc.available_stock,
            "published": doc.published}


# ---------------------------------------------------------------------------
# orders (SRS 2 - Order Acceptance/Rejection)
# ---------------------------------------------------------------------------
_ORDER_FIELDS = ["name", "order_type", "customer", "customer_name", "customer_phone",
                 "workflow_state", "grand_total", "currency", "payment_method",
                 "payment_status", "delivery_address", "delivery_zone",
                 "delivery_instructions", "prep_minutes", "ready_at", "creation"]


@frappe.whitelist()
def orders(state=None, merchant=None, limit=50):
    name = _merchant_or_throw(merchant)
    filters = {"merchant": name}
    if state:
        filters["workflow_state"] = state
    return frappe.get_all("Delivery Order", filters=filters, fields=_ORDER_FIELDS,
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist()
def pending_orders(merchant=None):
    """Inbox: orders waiting for acceptance."""
    name = _merchant_or_throw(merchant)
    return frappe.get_all("Delivery Order",
                          filters={"merchant": name, "workflow_state": "PENDING"},
                          fields=_ORDER_FIELDS, order_by="creation asc", limit=100)


@frappe.whitelist()
def order_detail(reference):
    order = _order(reference)
    return {
        "order": order.name,
        "state": order.workflow_state,
        "order_type": order.order_type,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "delivery_address": order.delivery_address,
        "delivery_instructions": order.delivery_instructions,
        "items": [{"item": i.item, "item_name": i.item_name, "qty": flt(i.qty),
                   "rate": flt(i.rate, 2), "amount": flt(i.amount, 2)}
                  for i in order.order_items],
        "items_total": flt(order.items_total, 2),
        "delivery_fee": flt(order.delivery_fee, 2),
        "small_order_fee": flt(order.small_order_fee, 2),
        "cod_fee": flt(order.cod_fee, 2),
        "grand_total": flt(order.grand_total, 2),
        "currency": order.currency,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "prep_minutes": order.prep_minutes,
        "ready_at": str(order.ready_at or ""),
    }


@frappe.whitelist()
def accept_order(order, prep_minutes=None):
    """SRS 3.1 step 3 - acceptance starts the prep timer."""
    doc = _order(order)
    doc.accept_order(prep_minutes=prep_minutes)
    return {"order": doc.name, "state": doc.workflow_state,
            "prep_minutes": doc.prep_minutes, "ready_at": str(doc.ready_at or "")}


@frappe.whitelist()
def reject_order(order, reason):
    doc = _order(order)
    doc.reject_order(reason)
    return {"order": doc.name, "state": doc.workflow_state}


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
@frappe.whitelist()
def stats(merchant=None):
    name = _merchant_or_throw(merchant)

    total = frappe.db.count("Delivery Order", {"merchant": name})
    # Frappe v16 rejects raw SQL aggregate strings in get_all() fields
    by_state_rows = frappe.db.sql(
        "SELECT workflow_state, COUNT(*) FROM `tabDelivery Order` "
        "WHERE merchant=%s GROUP BY workflow_state", name)

    revenue = frappe.db.sql(
        "SELECT COALESCE(SUM(grand_total),0) FROM `tabDelivery Order` "
        "WHERE merchant=%s AND workflow_state='COMPLETED'", name)[0][0]

    items = frappe.db.count("DL Menu Item", {"merchant": name})

    # what the platform owes this merchant: item amounts only
    # (service charges belong to the platform)
    payable_rows = frappe.db.sql(
        "SELECT COALESCE(SUM(items_total),0), COUNT(*) FROM `tabDelivery Order` "
        "WHERE merchant=%s AND workflow_state='COMPLETED'", name)
    payable = flt(payable_rows[0][0], 2)
    payable_orders = int(payable_rows[0][1] or 0)
    service_rows = frappe.db.sql(
        "SELECT COALESCE(SUM(service_fee_total),0) FROM `tabDelivery Order` "
        "WHERE merchant=%s AND workflow_state='COMPLETED'", name)

    return {"orders": total, "by_state": {r[0]: r[1] for r in by_state_rows},
            "completed_revenue": flt(revenue, 2), "catalog_items": items,
            "payable_to_merchant": payable,
            "payable_orders": payable_orders,
            "service_fees_collected": flt(service_rows[0][0], 2)}


# ---------------------------------------------------------------------------
# kitchen / readiness / payment updates
# ---------------------------------------------------------------------------
ACTIVE_ORDER_STATES = ("ACCEPTED", "PREPARING", "READY_FOR_DELIVERY",
                       "DRIVER_ASSIGNED", "PICKED_UP")

PAYMENT_STATUSES = ("Pending", "Authorized", "Paid", "Failed", "Refunded")


@frappe.whitelist()
def active_orders(merchant=None, limit=50):
    """Orders this merchant is preparing / waiting on (for the kitchen list)."""
    name = _merchant_or_throw(merchant)
    return frappe.get_all("Delivery Order",
                          filters={"merchant": name,
                                   "workflow_state": ["in", ACTIVE_ORDER_STATES]},
                          fields=["name", "workflow_state", "customer_name",
                                  "customer_phone", "grand_total", "currency",
                                  "payment_status", "payment_method",
                                  "assigned_driver", "ready_at"],
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist()
def start_preparing(order):
    """ACCEPTED -> PREPARING (used when an order was accepted without prep)."""
    doc = _order(order)
    if doc.workflow_state != "ACCEPTED":
        frappe.throw(_("Only an accepted order can start preparing "
                       "(currently {0}).").format(doc.workflow_state),
                     title=_("Wrong State"))
    from delivery.delivery_logistics import state_machine
    state_machine.set_state(doc, "PREPARING", note=_("Merchant started preparing"))
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"order": doc.name, "state": doc.workflow_state}


@frappe.whitelist()
def mark_ready(order):
    """PREPARING -> READY_FOR_DELIVERY: operations can now assign a driver."""
    doc = _order(order)
    doc.mark_ready_for_delivery()
    return {"order": doc.name, "state": doc.workflow_state}


@frappe.whitelist()
def set_order_payment(order, payment_status, payment_method=None):
    """Merchant records the real payment state on their own order
    (e.g. cash received -> Paid) and corrects the payment method."""
    doc = _order(order)
    if payment_status not in PAYMENT_STATUSES:
        frappe.throw(_("Payment status must be one of: {0}.")
                     .format(", ".join(PAYMENT_STATUSES)))
    if payment_method:
        valid_methods = [o.strip() for o in (frappe.get_meta("Delivery Order")
                         .get_field("payment_method").options or "").split("\n") if o.strip()]
        if payment_method not in valid_methods:
            frappe.throw(_("Payment method must be one of: {0}.")
                         .format(", ".join(valid_methods)))
        doc.payment_method = payment_method
    doc.payment_status = payment_status
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"order": doc.name, "payment_status": doc.payment_status,
            "payment_method": doc.payment_method}
