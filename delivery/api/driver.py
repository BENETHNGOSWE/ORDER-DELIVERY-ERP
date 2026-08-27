"""
Driver Web Dashboard API - SRS section 2 (Driver Web Dashboard).

A driver only ever sees jobs assigned to their own driver record, and the OTP
handoff plus Cash On Delivery settlement happen here (SRS 3.1 step 5).

Route prefix: /api/method/delivery.api.driver.*
"""
import frappe
from frappe import _
from frappe.utils import flt

from delivery.delivery_logistics import payments

#: Each service stores its address differently. Transport Request has no address
#: columns at all - its itinerary lives in the ``route_stops`` child table - so
#: the address column must be resolved per doctype rather than selected for
#: every table.
ADDRESS_COLS = {
    "Delivery Order": ("pickup_address", "delivery_address"),
    "Parcel Request": ("pickup_address", "dropoff_address"),
    "Transport Request": (),
}

AMOUNT_FIELD = {
    "Delivery Order": "grand_total",
    "Parcel Request": "tariff_amount",
    "Transport Request": "agreed_price",
}

SERVICE_LABEL = {
    "Delivery Order": "order_type",
    "Parcel Request": "Parcel",
    "Transport Request": "Transport",
}


# ---------------------------------------------------------------------------
# scoping
# ---------------------------------------------------------------------------
def _require_login():
    if frappe.session.user in ("", "Guest"):
        frappe.throw(_("Please log in."), frappe.AuthenticationError)
    return frappe.session.user


def _driver_for(user=None):
    """The Delivery Driver record belonging to this login."""
    user = user or _require_login()
    code = frappe.db.get_value("Delivery Driver", {"user": user}, "name")
    if not code:
        frappe.throw(_("Your login is not linked to a driver profile."),
                     frappe.PermissionError)
    return code


def _job(reference, user=None):
    """Load a job and assert it belongs to this driver."""
    code = _driver_for(user)
    for dt in AMOUNT_FIELD:
        if frappe.db.exists(dt, reference):
            doc = frappe.get_doc(dt, reference)
            if doc.get("assigned_driver") != code:
                frappe.throw(_("This job is not assigned to you."),
                             frappe.PermissionError)
            return dt, doc
    frappe.throw(_("No job found with reference {0}.").format(reference),
                 frappe.DoesNotExistError)


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------
@frappe.whitelist()
def profile():
    code = _driver_for()
    d = frappe.get_doc("Delivery Driver", code)
    return {"driver": d.name, "driver_code": d.driver_code,
            "driver_name": d.driver_name, "phone": d.phone,
            "vehicle_type": d.vehicle_type, "vehicle_plate": d.vehicle_plate,
            "status": d.status, "max_load_kg": flt(d.max_load_kg, 2),
            "base_zone": d.base_zone, "rating": flt(d.rating, 2),
            "capabilities": {"food": bool(d.can_food), "parcel": bool(d.can_parcel),
                             "transport": bool(d.can_transport)}}


@frappe.whitelist()
def set_availability(status):
    """Available / On Trip / Offline."""
    code = _driver_for()
    if status not in ("Available", "On Trip", "Offline"):
        frappe.throw(_("Unknown availability status: {0}").format(status),
                     title=_("Invalid Status"))
    frappe.db.set_value("Delivery Driver", code, "status", status)
    frappe.db.commit()
    return {"driver": code, "status": status}


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------
@frappe.whitelist()
def my_jobs(state=None, limit=30):
    """Active jobs across all three services."""
    code = _driver_for()
    active = ["DRIVER_ASSIGNED", "PICKED_UP"]
    jobs = []

    for dt in AMOUNT_FIELD:
        amount_field = AMOUNT_FIELD[dt]
        filters = {"assigned_driver": code}
        filters["workflow_state"] = state or ["in", active + ["ACCEPTED", "PREPARING"]]
        fields = (["name", "workflow_state", "creation", "currency",
                   "payment_status", amount_field] + list(ADDRESS_COLS[dt]))

        rows = frappe.get_all(dt, filters=filters, fields=fields,
                              order_by="creation asc", limit=int(limit))
        for r in rows:
            address = None
            for col in ADDRESS_COLS[dt]:
                address = address or r.get(col)

            if dt == "Transport Request":
                # the first stop is the origin
                address = frappe.db.get_value(
                    "Transport Stop",
                    {"parent": r.name, "parenttype": "Transport Request"},
                    "address", order_by="idx asc")

            service = SERVICE_LABEL[dt]
            if dt == "Delivery Order":
                service = frappe.db.get_value(dt, r.name, "order_type") or "Food"

            jobs.append({
                "reference": r.name,
                "doctype": dt,
                "service": service,
                "state": r.workflow_state,
                "amount": flt(r.get(amount_field), 2),
                "currency": r.currency,
                "payment_status": r.payment_status,
                "address": address,
                "created": str(r.creation),
            })

    jobs.sort(key=lambda j: j["created"])
    return jobs


@frappe.whitelist()
def job_detail(reference):
    dt, doc = _job(reference)
    data = doc.get_tracking()
    data["doctype"] = dt

    if dt == "Transport Request":
        data["stops"] = [{"idx": s.idx, "idx_label": s.idx_label, "address": s.address,
                          "stop_type": s.stop_type, "status": s.status,
                          "distance_from_prev_km": flt(s.distance_from_prev_km, 2),
                          "contact_name": s.contact_name,
                          "contact_phone": s.contact_phone}
                         for s in doc.route_stops]
        data["current_stop_index"] = int(doc.current_stop_index or 0)
    elif dt == "Delivery Order":
        data["items"] = [{"item_name": i.item_name, "qty": flt(i.qty)}
                         for i in doc.order_items]
        data["delivery_instructions"] = doc.delivery_instructions

    data["customer_phone"] = doc.get("customer_phone")
    return data


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------
@frappe.whitelist()
def confirm_pickup(reference):
    dt, doc = _job(reference)
    if dt == "Transport Request":
        doc.start_trip()
    else:
        doc.confirm_pickup()
    return {"reference": reference, "state": doc.workflow_state}


@frappe.whitelist()
def complete_handoff(reference, otp=None, collected_amount=0):
    """
    Proof of delivery (SRS 3.1 step 5).

    Verifies the customer's 4-digit code and, for Cash On Delivery, settles the
    Payment Transaction so the collected cash is recorded against the handoff.
    """
    dt, doc = _job(reference)

    if dt == "Transport Request":
        doc.complete_trip()
        return {"reference": reference, "state": doc.workflow_state}

    before = doc.payment_status
    doc.complete_handoff(otp=otp, collected_amount=collected_amount)

    frappe.db.set_value("Delivery Driver", doc.assigned_driver, "status", "Available")

    return {"reference": reference, "state": doc.workflow_state,
            "payment_status": doc.payment_status,
            "collected": flt(collected_amount, 2),
            "settled": before != doc.payment_status}


@frappe.whitelist()
def advance_transport_stop(reference, stop_index=None, note=None):
    dt, doc = _job(reference)
    if dt != "Transport Request":
        frappe.throw(_("Only transport trips have an itinerary."),
                     title=_("Not A Trip"))
    return doc.advance_stop(stop_index=stop_index, note=note)


# ---------------------------------------------------------------------------
# earnings
# ---------------------------------------------------------------------------
@frappe.whitelist()
def my_earnings(from_date=None, to_date=None):
    """Remittance ledger: every payment transaction on this driver's jobs."""
    code = _driver_for()
    refs = []
    for dt in AMOUNT_FIELD:
        refs += [(dt, r) for r in frappe.get_all(
            dt, filters={"assigned_driver": code}, pluck="name", limit=500)]

    rows = []
    for dt, name in refs:
        for t in frappe.get_all("Payment Transaction",
                                filters={"reference_doctype": dt,
                                         "reference_name": name},
                                fields=["name", "payment_method", "payment_status",
                                        "amount", "collected_amount", "currency",
                                        "paid_on"]):
            rows.append(t)

    total = sum(flt(r.amount) for r in rows if r.payment_status == "Paid")
    return {"driver": code, "transactions": rows,
            "settled_total": flt(total, 2), "count": len(rows)}
