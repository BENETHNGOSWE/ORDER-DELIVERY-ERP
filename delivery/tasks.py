"""
Scheduled jobs.

The SRS web scope needs almost no background work; the one thing that does
require it is expiring transport quotes that were never accepted, so staff are
not chasing a fare the customer has already walked away from.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime


def expire_transport_quotes():
    """
    Cancel transport quotes past their validity window.

    Only ``PRICE_AGREED`` requests are touched - anything already accepted,
    dispatched or closed is left alone.
    """
    stale = frappe.get_all(
        "Transport Request",
        filters={"workflow_state": "PRICE_AGREED",
                 "quote_expires_on": ["<", now_datetime()]},
        pluck="name", limit=200)

    for name in stale:
        try:
            req = frappe.get_doc("Transport Request", name)
            req.cancel_document(_("Quote expired without customer approval"))
        except frappe.ValidationError:
            frappe.log_error(
                title=_("Could not expire transport quote {0}").format(name),
                message=frappe.get_traceback())

    if stale:
        frappe.db.commit()
    return len(stale)
