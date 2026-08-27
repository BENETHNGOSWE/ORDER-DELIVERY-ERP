"""
Operations Web Portal API - SRS section 2 (Operations Web Portal).

Covers the three staff-only jobs the SRS calls out: reviewing parcels that need
a manual tariff, negotiating and recording transport fares, and assigning
drivers. Also owns platform settings.

Route prefix: /api/method/delivery.api.operations.*
"""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from delivery.delivery_logistics import billing, state_machine

SERVICE_DOCTYPES = ("Delivery Order", "Parcel Request", "Transport Request")


# ---------------------------------------------------------------------------
# scoping
# ---------------------------------------------------------------------------
def _require_ops():
    user = frappe.session.user
    if user in ("", "Guest"):
        frappe.throw(_("Please log in."), frappe.AuthenticationError)
    if not ({"System Manager", "Delivery Operations"} & set(frappe.get_roles())):
        frappe.throw(_("Operations access is required."), frappe.PermissionError)
    return user


def _doc(doctype, name):
    if not frappe.db.exists(doctype, name):
        frappe.throw(_("No {0} named {1}.").format(doctype, name),
                     frappe.DoesNotExistError)
    return frappe.get_doc(doctype, name)


def _find(reference):
    """Resolve any reference across the three service doctypes."""
    for dt in SERVICE_DOCTYPES:
        if frappe.db.exists(dt, reference):
            return dt, frappe.get_doc(dt, reference)
    frappe.throw(_("No order or request found with reference {0}.").format(reference),
                 frappe.DoesNotExistError)


# ---------------------------------------------------------------------------
# review queue (SRS 3.2 manual quote / 3.3 staff review)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def review_queue(limit=50):
    """Parcels needing a manual tariff plus transport requests awaiting review."""
    _require_ops()

    parcels = frappe.get_all(
        "Parcel Request", filters={"workflow_state": "UNDER_REVIEW"},
        fields=["name", "customer_name", "customer_phone", "weight_kg",
                "length_cm", "width_cm", "height_cm", "is_fragile",
                "is_heavy", "is_oversized", "weight_category", "distance_km",
                "parcel_description", "creation"],
        order_by="creation asc", limit=int(limit))

    transport = frappe.get_all(
        "Transport Request", filters={"workflow_state": "UNDER_REVIEW"},
        fields=["name", "customer_name", "customer_phone", "trip_type",
                "vehicle_type", "passengers", "total_distance_km",
                "suggested_fare", "currency", "departure_datetime", "creation"],
        order_by="creation asc", limit=int(limit))

    return {"parcels": parcels, "transport": transport,
            "count": len(parcels) + len(transport)}


@frappe.whitelist()
def transport_detail(reference):
    """Full itinerary + negotiation history for one transport request."""
    _require_ops()
    req = _doc("Transport Request", reference)
    return {
        "request": req.name,
        "state": req.workflow_state,
        "customer_name": req.customer_name,
        "customer_phone": req.customer_phone,
        "trip_type": req.trip_type,
        "vehicle_type": req.vehicle_type,
        "passengers": req.passengers,
        "luggage_pieces": req.luggage_pieces,
        "special_requirements": req.special_requirements,
        "departure_datetime": str(req.departure_datetime or ""),
        "total_distance_km": flt(req.total_distance_km, 2),
        "suggested_fare": flt(req.suggested_fare, 2),
        "agreed_price": flt(req.agreed_price, 2),
        "negotiation_note": req.negotiation_note,
        "quoted_by": req.quoted_by,
        "quote_expires_on": str(req.quote_expires_on or ""),
        "currency": req.currency,
        "payment_status": req.payment_status,
        "assigned_driver": req.assigned_driver,
        "stops": [{"idx": s.idx, "idx_label": s.idx_label, "address": s.address,
                   "stop_type": s.stop_type,
                   "distance_from_prev_km": flt(s.distance_from_prev_km, 2),
                   "status": s.status, "contact_name": s.contact_name,
                   "contact_phone": s.contact_phone}
                  for s in req.route_stops],
        "timeline": state_machine.timeline(req),
    }


# ---------------------------------------------------------------------------
# parcel tariff (SRS 3.2)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def set_parcel_tariff(parcel, amount, note=None):
    _require_ops()
    doc = _doc("Parcel Request", parcel)
    doc.set_tariff(amount, note)
    return {"parcel": doc.name, "state": doc.workflow_state,
            "tariff_amount": flt(doc.tariff_amount, 2), "currency": doc.currency}


@frappe.whitelist()
def reject_parcel(parcel, reason):
    _require_ops()
    doc = _doc("Parcel Request", parcel)
    doc.reject_parcel(reason)
    return {"parcel": doc.name, "state": doc.workflow_state}


# ---------------------------------------------------------------------------
# transport negotiation (SRS 3.3 steps 3-4)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def log_agreed_price(reference, amount, note=None):
    """Record the fare agreed with the customer over the phone."""
    user = _require_ops()
    req = _doc("Transport Request", reference)
    req.log_agreed_price(amount, note=note, by=user)
    return {"request": req.name, "state": req.workflow_state,
            "agreed_price": flt(req.agreed_price, 2),
            "quote_expires_on": str(req.quote_expires_on or ""),
            "currency": req.currency}


@frappe.whitelist()
def record_contact(reference, note):
    """Log that staff called the customer (audit trail for the negotiation)."""
    _require_ops()
    dt, doc = _find(reference)
    state_machine.append_history(doc, doc.workflow_state,
                                 note=_("Contact logged: {0}").format(note))
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"reference": reference, "logged": True}


# ---------------------------------------------------------------------------
# dispatch (SRS 3.1 step 4 / 3.2 / 3.3 step 6)
# ---------------------------------------------------------------------------
_CAPABILITY = {"Delivery Order": "can_food",
               "Parcel Request": "can_parcel",
               "Transport Request": "can_transport"}


@frappe.whitelist()
def available_drivers(reference=None, service=None):
    """Drivers who are free and capable of this job."""
    _require_ops()
    filters = {"status": ["in", ["Available", "On Trip"]]}

    dt = None
    if reference:
        dt, _ = _find(reference)
    cap = _CAPABILITY.get(dt) or {"Food": "can_food", "Retail": "can_food",
                                  "Parcel": "can_parcel",
                                  "Transport": "can_transport"}.get(service)
    if cap:
        filters[cap] = 1

    return frappe.get_all("Delivery Driver", filters=filters,
                          fields=["name", "driver_code", "driver_name", "phone",
                                  "vehicle_type", "vehicle_plate", "status",
                                  "max_load_kg", "base_zone", "rating"],
                          order_by="rating desc, driver_name asc", limit=50)


@frappe.whitelist()
def suggest_driver(reference):
    """Best-fit driver: capable, free, and rated highest."""
    _require_ops()
    drivers = available_drivers(reference=reference)
    return drivers[0] if drivers else None


@frappe.whitelist()
def assign_driver(reference, driver, trip=None):
    _require_ops()
    dt, doc = _find(reference)

    if doc.workflow_state not in ("ACCEPTED", "PREPARING"):
        frappe.throw(_("{0} must be accepted before a driver is assigned "
                       "(currently {1}).").format(reference, doc.workflow_state),
                     title=_("Wrong State"))

    doc.assign_driver(driver, trip=trip)
    return {"reference": reference, "state": doc.workflow_state,
            "driver": driver, "otp_code": doc.get("otp_code")}


# ---------------------------------------------------------------------------
# dashboards / settings
# ---------------------------------------------------------------------------
@frappe.whitelist()
def dashboard():
    """Cross-service operational overview."""
    _require_ops()

    # Frappe v16 rejects raw SQL aggregate strings in get_all() fields, so the
    # grouped counts are read with plain SQL instead.
    def counts(dt):
        rows = frappe.db.sql(
            "SELECT workflow_state, COUNT(*) FROM `tab{0}` "
            "GROUP BY workflow_state".format(dt))
        return {r[0]: r[1] for r in rows}

    def revenue(dt, field):
        return flt(frappe.db.sql(
            "SELECT COALESCE(SUM({0}),0) FROM `tab{1}` "
            "WHERE workflow_state='COMPLETED'".format(field, dt))[0][0], 2)

    orders = counts("Delivery Order")
    parcels = counts("Parcel Request")
    transport = counts("Transport Request")

    s = billing.settings()
    return {
        "currency": s.currency,
        "orders": {"total": sum(orders.values()), "by_state": orders,
                   "revenue": revenue("Delivery Order", "grand_total")},
        "parcels": {"total": sum(parcels.values()), "by_state": parcels,
                    "revenue": revenue("Parcel Request", "tariff_amount")},
        "transport": {"total": sum(transport.values()), "by_state": transport,
                      "revenue": revenue("Transport Request", "agreed_price")},
        "awaiting_review": frappe.db.count("Parcel Request",
                                           {"workflow_state": "UNDER_REVIEW"})
                           + frappe.db.count("Transport Request",
                                             {"workflow_state": "UNDER_REVIEW"}),
        "unassigned": frappe.db.count("Delivery Order",
                                      {"workflow_state": ["in", ["ACCEPTED", "PREPARING"]]})
                      + frappe.db.count("Parcel Request",
                                        {"workflow_state": ["in", ["ACCEPTED", "PREPARING"]]})
                      + frappe.db.count("Transport Request",
                                        {"workflow_state": ["in", ["ACCEPTED", "PREPARING"]]}),
        "drivers_available": frappe.db.count("Delivery Driver", {"status": "Available"}),
        "merchants_open": frappe.db.count("Merchant", {"status": "Open"}),
    }


@frappe.whitelist()
def all_documents(doctype, limit=50, state=None):
    """Generic listing for the operations console."""
    _require_ops()
    if doctype not in SERVICE_DOCTYPES:
        frappe.throw(_("Unsupported document type: {0}").format(doctype),
                     title=_("Not Allowed"))
    filters = {"workflow_state": state} if state else {}
    return frappe.get_all(doctype, filters=filters,
                          fields=["name", "workflow_state", "customer",
                                  "creation", "payment_status"],
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist()
def update_settings(**changes):
    _require_ops()
    s = billing.settings()

    numeric = {"base_delivery_fee", "per_km_fee", "min_delivery_fee",
               "small_order_fee", "small_order_threshold", "free_delivery_over",
               "parcel_base_fee", "parcel_per_km_fee", "fragile_surcharge_pct",
               "instant_weight_limit_kg", "max_instant_dimension_cm",
               "transport_base_fare", "transport_per_km", "transport_per_stop",
               "cod_fee", "default_commission_rate", "transport_commission_rate",
               "parcel_margin_rate"}
    integers = {"quote_validity_hours", "default_prep_minutes",
                "driver_max_active_jobs"}
    flags = {"enabled", "cod_enabled", "mpesa_enabled", "tigo_pesa_enabled",
             "card_enabled", "simulate_payment_gateways", "auto_assign_driver"}

    for key, value in changes.items():
        if key in numeric:
            s.set(key, flt(value))
        elif key in integers:
            s.set(key, int(flt(value)))
        elif key in flags:
            s.set(key, int(value))
        elif key in ("platform_name", "currency", "language", "country"):
            s.set(key, value)

    s.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache()
    return {"updated": True, "currency": s.currency}
