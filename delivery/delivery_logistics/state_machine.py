"""
Master order state machine - SRS v2.2.0 section 5.

This module is the SINGLE SOURCE OF TRUTH for the order lifecycle. Nothing else
in the app writes ``workflow_state`` directly; every transition goes through
:func:`set_state`, which validates the move, appends to the JSON audit trail and
fires the side effects (timestamps, OTP, payment settlement).

The nine states
---------------
    REQUESTED -> UNDER_REVIEW -> PRICE_AGREED -> PENDING -> ACCEPTED
              -> PREPARING -> DRIVER_ASSIGNED -> PICKED_UP -> COMPLETED
                                                        (+ CANCELLED)

Not every state applies to every service. The SRS marks the inapplicable ones
"n/a"; ``SERVICE_ENTRY`` and ``SERVICE_LABELS`` encode the per-service view so
the portals can render human wording ("Kitchen/Packing" vs "Vehicle Prep").
"""
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

# ---------------------------------------------------------------------------
# states
# ---------------------------------------------------------------------------
STATES = [
    "REQUESTED",
    "UNDER_REVIEW",
    "PRICE_AGREED",
    "PENDING",
    "ACCEPTED",
    "PREPARING",
    "DRIVER_ASSIGNED",
    "PICKED_UP",
    "COMPLETED",
    "CANCELLED",
]

TERMINAL = ("COMPLETED", "CANCELLED")

#: Legal forward moves. CANCELLED is reachable from every non-terminal state.
ALLOWED = {
    "REQUESTED":       ["UNDER_REVIEW", "PRICE_AGREED", "PENDING", "CANCELLED"],
    "UNDER_REVIEW":    ["PRICE_AGREED", "CANCELLED"],
    "PRICE_AGREED":    ["PENDING", "ACCEPTED", "CANCELLED"],
    "PENDING":         ["ACCEPTED", "CANCELLED"],
    "ACCEPTED":        ["PREPARING", "DRIVER_ASSIGNED", "CANCELLED"],
    "PREPARING":       ["DRIVER_ASSIGNED", "PICKED_UP", "CANCELLED"],
    "DRIVER_ASSIGNED": ["PICKED_UP", "CANCELLED"],
    "PICKED_UP":       ["COMPLETED", "CANCELLED"],
    "COMPLETED":       [],
    "CANCELLED":       [],
}

# ---------------------------------------------------------------------------
# per-service views (SRS section 5 table)
# ---------------------------------------------------------------------------
#: State a newly created document lands in, by service.
SERVICE_ENTRY = {
    "Food": "PENDING",
    "Retail": "PENDING",
    "Parcel": "REQUESTED",
    "Transport": "UNDER_REVIEW",
}

#: States that do not apply to a service ("n/a" in the SRS matrix).
SERVICE_NOT_APPLICABLE = {
    "Food": ("REQUESTED", "UNDER_REVIEW", "PRICE_AGREED"),
    "Retail": ("REQUESTED", "UNDER_REVIEW", "PRICE_AGREED"),
    "Parcel": (),
    "Transport": (),
}

#: Human wording per service, exactly as tabulated in the SRS.
SERVICE_LABELS = {
    "Food": {
        "PENDING": _("Awaiting Merchant"),
        "ACCEPTED": _("Order Confirmed"),
        "PREPARING": _("Kitchen/Packing"),
        "DRIVER_ASSIGNED": _("Driver Assigned"),
        "PICKED_UP": _("In Transit"),
        "COMPLETED": _("Delivered"),
    },
    "Retail": {
        "PENDING": _("Awaiting Merchant"),
        "ACCEPTED": _("Order Confirmed"),
        "PREPARING": _("Kitchen/Packing"),
        "DRIVER_ASSIGNED": _("Driver Assigned"),
        "PICKED_UP": _("In Transit"),
        "COMPLETED": _("Delivered"),
    },
    "Parcel": {
        "REQUESTED": _("Details Submitted"),
        "UNDER_REVIEW": _("Manual Quote"),
        "PRICE_AGREED": _("Quote Set"),
        "PENDING": _("Awaiting Payment"),
        "ACCEPTED": _("Order Confirmed"),
        "PREPARING": _("Package Prep"),
        "DRIVER_ASSIGNED": _("Driver Assigned"),
        "PICKED_UP": _("In Transit"),
        "COMPLETED": _("Delivered"),
    },
    "Transport": {
        "REQUESTED": _("Route Submitted"),
        "UNDER_REVIEW": _("Staff Reviewing"),
        "PRICE_AGREED": _("Fare Negotiated"),
        "PENDING": _("Awaiting Payment"),
        "ACCEPTED": _("Job Confirmed"),
        "PREPARING": _("Vehicle Prep"),
        "DRIVER_ASSIGNED": _("Driver Assigned"),
        "PICKED_UP": _("Route Active"),
        "COMPLETED": _("Trip Completed"),
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def service_of(doc):
    """Map any service document onto one of the four service keys."""
    dt = getattr(doc, "doctype", None)
    if dt == "Delivery Order":
        return doc.get("order_type") or "Food"
    if dt == "Parcel Request":
        return "Parcel"
    if dt == "Transport Request":
        return "Transport"
    return doc.get("service") or "Food"


def label_for(doc, state):
    """Human wording for ``state`` in this document's service."""
    return SERVICE_LABELS.get(service_of(doc), {}).get(state, state.replace("_", " ").title())


def applicable_states(doc):
    """Ordered states that apply to this document's service."""
    svc = service_of(doc)
    skip = SERVICE_NOT_APPLICABLE.get(svc, ())
    return [s for s in STATES if s != "CANCELLED" and s not in skip]


def can_transition(current, target):
    return target in ALLOWED.get(current, [])


def next_states(current):
    return list(ALLOWED.get(current, []))


# ---------------------------------------------------------------------------
# audit trail
# ---------------------------------------------------------------------------
def _history(doc):
    raw = doc.get("status_history")
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def append_history(doc, state, note=None, by=None):
    entry = {
        "state": state,
        "label": label_for(doc, state),
        "timestamp": str(now_datetime()),
        "by": by or getattr(frappe.session, "user", None) or "System",
    }
    if note:
        entry["note"] = str(note)[:500]
    history = _history(doc) + [entry]
    doc.status_history = json.dumps(history, indent=1, default=str)
    return entry


def timeline(doc):
    """Public, sanitised audit trail (used by /track)."""
    return [
        {"state": h.get("state"), "label": h.get("label"),
         "timestamp": h.get("timestamp"), "by": h.get("by"),
         "note": h.get("note")}
        for h in _history(doc)
    ]


# ---------------------------------------------------------------------------
# the mutator
# ---------------------------------------------------------------------------
def set_state(doc, target, note=None, by=None, force=False):
    """
    Move ``doc`` to ``target``.

    Validates the move against :data:`ALLOWED`, records the audit entry and
    applies the side effects that belong to the new state. Callers never touch
    ``workflow_state`` themselves.

    ``force`` is reserved for data migration and bypasses the transition check
    (it still writes the audit trail).
    """
    current = doc.get("workflow_state")

    if target not in STATES:
        frappe.throw(_("Unknown state: {0}").format(target), title=_("Invalid State"))

    if not current:
        # first write - allow any entry state for the service
        doc.workflow_state = target
        append_history(doc, target, note, by)
        return _side_effects(doc, target)

    if current == target:
        return doc

    if not force and not can_transition(current, target):
        frappe.throw(
            _("{0} cannot move from {1} to {2}.").format(
                doc.get("name") or _("This document"), current, target),
            title=_("Invalid State Transition"),
        )

    doc.workflow_state = target
    append_history(doc, target, note, by)
    return _side_effects(doc, target)


def _side_effects(doc, state):
    """Timestamps and flags that belong to a given state."""
    stamp = now_datetime()

    if state == "PICKED_UP" and not doc.get("picked_up_at"):
        doc.picked_up_at = stamp

    if state == "COMPLETED":
        if not doc.get("completed_at"):
            doc.completed_at = stamp
        if doc.get("payment_method") == "Cash On Delivery" and \
                doc.get("payment_status") in (None, "", "Pending"):
            doc.payment_status = "Paid"

    if state == "DRIVER_ASSIGNED" and doc.get("assigned_driver"):
        doc.otp_code = doc.get("otp_code") or _new_otp()

    return doc


def _new_otp():
    """4-digit handoff code (SRS 3.1 step 5 - proof of delivery)."""
    import random
    return "{0:04d}".format(random.randint(0, 9999))
