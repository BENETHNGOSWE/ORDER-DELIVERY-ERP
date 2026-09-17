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

    if doc.workflow_state not in ("ACCEPTED", "PREPARING", "READY_FOR_DELIVERY"):
        frappe.throw(_("{0} must be ready before a driver is assigned "
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
                                      {"workflow_state": ["in", ["ACCEPTED", "PREPARING", "READY_FOR_DELIVERY"]]})
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


# ---------------------------------------------------------------------------
# reports (admin dashboard box 9)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def reports(from_date=None, to_date=None):
    """Time-based financial reporting.

    With from_date/to_date (YYYY-MM-DD) every section - KPI totals, merchant
    payables, platform revenue - is computed ONLY from orders created inside
    that period. Without dates it defaults to today, so the dashboard always
    answers 'what happened in the selected period'.

    Also returns the fixed overview windows (today / last 7 days / month /
    all time) for the period table, and the recent orders behind the numbers.
    """
    from delivery.delivery_logistics import billing
    from frappe.utils import nowdate
    from datetime import datetime, timedelta

    def window(days=None, month_start=False):
        """'YYYY-MM-DD' string - plain stdlib date math; some frappe builds
        return str (not date) from get_first_day/add_days, so .strftime on
        their results crashes with 'str has no attribute strftime'."""
        d = datetime.strptime(nowdate(), "%Y-%m-%d").date()
        if month_start:
            d = d.replace(day=1)
        elif days:
            d = d - timedelta(days=days)
        return d.strftime("%Y-%m-%d")

    # ---- resolve the selected reporting period (default: today) ----
    def _clean(x):
        x = (x or "").strip()
        if not x:
            return None
        try:
            return datetime.strptime(x[:10], "%Y-%m-%d").date().strftime("%Y-%m-%d")
        except Exception:
            return None
    fd, td = _clean(from_date), _clean(to_date)
    if fd and not td:
        td = fd
    if td and not fd:
        fd = td
    if not fd:
        fd = td = nowdate()[:10]

    def stats(since=None):
        f = {"workflow_state": "COMPLETED"}
        if since:
            f["creation"] = [">=", since]
        rows = frappe.get_all("Delivery Order", filters=f,
                              fields=["grand_total", "items_total",
                                      "service_fee_total", "delivery_fee"])
        return {"orders": len(rows),
                "grand_total": round(sum(flt(r.grand_total) for r in rows), 2),
                "items_total": round(sum(flt(r.items_total) for r in rows), 2),
                "service_fee_total": round(sum(flt(r.service_fee_total) for r in rows), 2),
                "delivery_fees": round(sum(flt(r.delivery_fee) for r in rows), 2)}

    completed_all = frappe.get_all("Delivery Order",
                                   filters={"workflow_state": "COMPLETED",
                                            "creation": ["between", [fd + " 00:00:00", td + " 23:59:59"]]},
                                   fields=["name", "creation", "merchant", "items_total",
                                           "service_fee_total", "delivery_fee", "grand_total",
                                           "payment_status"])
    payables = {}
    for r in completed_all:
        m = r.merchant or "Unknown"
        payables.setdefault(m, {"items_total": 0.0, "service_fee": 0.0,
                                "grand_total": 0.0, "orders": 0})
        payables[m]["items_total"] += flt(r.items_total)
        payables[m]["service_fee"] += flt(r.service_fee_total)
        payables[m]["grand_total"] += flt(r.items_total) + flt(r.service_fee_total)
        payables[m]["orders"] += 1

    names = list(payables)
    mnames = {m["name"]: m["merchant_name"] for m in
              frappe.get_all("Merchant", filters={"name": ["in", names]},
                             fields=["name", "merchant_name"])} if names else {}
    share = billing.driver_fee_share_pct()
    all_fees = sum(flt(r.delivery_fee) for r in completed_all)

    sel_orders = len(completed_all)
    sel_items = round(sum(flt(r.items_total) for r in completed_all), 2)
    sel_service = round(sum(flt(r.service_fee_total) for r in completed_all), 2)
    sel_fees = round(sum(flt(r.delivery_fee) for r in completed_all), 2)
    sel_grand = round(sum(flt(r.grand_total) for r in completed_all), 2)
    recent = [{"name": r.name,
               "date": str(r.creation)[:16] if r.creation else "",
               "merchant": mnames.get(r.merchant, r.merchant or "-"),
               "items_total": flt(r.items_total), "service_fee_total": flt(r.service_fee_total),
               "delivery_fee": flt(r.delivery_fee), "grand_total": flt(r.grand_total),
               "payment_status": r.payment_status or "Pending"}
              for r in sorted(completed_all, key=lambda x: str(x.creation), reverse=True)[:50]]

    return {
        "currency": billing.settings().currency,
        "period": {"from": fd, "to": td},
        "selected": {"orders": sel_orders, "items_total": sel_items,
                     "service_fee_total": sel_service, "delivery_fees": sel_fees,
                     "grand_total": sel_grand},
        "today": stats(window()),
        "week": stats(window(days=7)),
        "month": stats(window(month_start=True)),
        "all_time": stats(),
        "merchant_payables": [
            {"merchant": m, "merchant_name": mnames.get(m, m),
             "orders": v["orders"],
             "payable": round(v["items_total"], 2),
             "service_fee": round(v["service_fee"], 2),
             "order_total": round(v["grand_total"], 2)}
            for m, v in sorted(payables.items(),
                               key=lambda kv: -kv[1]["items_total"])],
        "platform_revenue": {
            "delivery_office_share": round(sel_fees * (100 - share) / 100.0, 2),
            "service_fees": sel_service,
            "total": round(sel_fees * (100 - share) / 100.0 + sel_service, 2),
        },
        "driver_share_pct": share,
        "recent_orders": recent,
    }


@frappe.whitelist()
def driver_payouts(from_date=None, to_date=None):
    """Per-driver payout for the SELECTED period: driver's share (e.g. 70%)
    of delivery fees on completed deliveries. Defaults to today."""
    from delivery.delivery_logistics import billing
    from frappe.utils import nowdate
    from datetime import datetime
    def _clean(x):
        x = (x or "").strip()
        if not x:
            return None
        try:
            return datetime.strptime(x[:10], "%Y-%m-%d").date().strftime("%Y-%m-%d")
        except Exception:
            return None
    fd, td = _clean(from_date), _clean(to_date)
    if fd and not td:
        td = fd
    if not fd:
        fd = td = nowdate()[:10]
    share = billing.driver_fee_share_pct()
    rows = frappe.get_all("Delivery Order",
                          filters={"workflow_state": "COMPLETED",
                                   "assigned_driver": ["is", "set"],
                                   "creation": ["between", [fd + " 00:00:00", td + " 23:59:59"]]},
                          fields=["assigned_driver", "delivery_fee"])
    agg = {}
    for r in rows:
        agg.setdefault(r.assigned_driver, {"jobs": 0, "fees": 0.0})
        agg[r.assigned_driver]["jobs"] += 1
        agg[r.assigned_driver]["fees"] += flt(r.delivery_fee)
    names = list(agg)
    dnames = {d["name"]: d for d in
              frappe.get_all("Delivery Driver", filters={"name": ["in", names]},
                             fields=["name", "driver_name", "phone"])} if names else {}
    out = []
    for code, v in agg.items():
        info = dnames.get(code, {})
        out.append({"driver": code, "driver_name": info.get("driver_name", code),
                    "phone": info.get("phone"), "jobs": v["jobs"],
                    "fees_total": round(v["fees"], 2),
                    "share_pct": share,
                    "payable": round(v["fees"] * share / 100.0, 2)})
    out = sorted(out, key=lambda x: -x["payable"])
    return {"from": fd, "to": td, "share_pct": share,
            "total_payable": round(sum(o["payable"] for o in out), 2),
            "drivers": out}
