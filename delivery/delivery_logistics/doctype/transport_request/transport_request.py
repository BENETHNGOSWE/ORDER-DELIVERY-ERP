"""Transport Request - negotiated multi-stop transport routing (SRS 3.3)."""
import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime

from delivery.delivery_logistics import billing, payments, state_machine
from delivery.delivery_logistics.base import ServiceDocument


class TransportRequest(ServiceDocument):
    SERVICE = "Transport"
    #: the binding figure is what staff agreed, never the suggested fare
    AMOUNT_FIELD = "agreed_price"

    def validate(self):
        billing.apply_currency(self)

        if len(self.get("route_stops") or []) < 2:
            frappe.throw(_("An itinerary needs at least an origin and a destination."),
                         title=_("Incomplete Itinerary"))

        self.total_distance_km = billing.transport_distance(self)
        self.suggested_fare = billing.transport_suggested_fare(self)

        if not self.get("payment_status"):
            self.payment_status = "Pending"

        if not self.get("workflow_state"):
            # SRS 3.3: every trip is reviewed by staff before a fare is agreed
            state_machine.set_state(self, "UNDER_REVIEW",
                                    note=_("Route submitted - staff reviewing"))

    # -- negotiation (SRS 3.3 steps 3-4) ---------------------------------
    def log_agreed_price(self, amount, note=None, by=None):
        """
        Staff record the fare agreed over the phone.

        This is the only thing that makes a transport price binding -
        ``suggested_fare`` is an estimate and is never charged.
        """
        amount = flt(amount)
        if amount <= 0:
            frappe.throw(_("The agreed fare must be greater than zero."),
                         title=_("Invalid Fare"))
        if self.workflow_state not in ("UNDER_REVIEW", "REQUESTED", "PRICE_AGREED"):
            frappe.throw(_("A fare can only be agreed before the trip is accepted."),
                         title=_("Wrong State"))

        self.agreed_price = billing.r2(amount)
        self.negotiation_note = note
        self.quoted_by = by or frappe.session.user
        self.quoted_on = now_datetime()
        self.quote_expires_on = add_to_date(now_datetime(),
                                            hours=billing.quote_validity_hours())

        state_machine.set_state(self, "PRICE_AGREED",
                                note=_("Fare agreed: {0}").format(self.agreed_price))
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self

    def approve_quote(self):
        """SRS 3.3 step 5 - the customer accepts the agreed fare."""
        if not flt(self.agreed_price):
            frappe.throw(_("A fare must be agreed before this trip can be approved."),
                         title=_("No Agreed Fare"))
        if self.workflow_state != "PRICE_AGREED":
            frappe.throw(_("This trip is not awaiting approval."),
                         title=_("Wrong State"))
        state_machine.set_state(self, "ACCEPTED", note=_("Customer approved the quote"))
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self

    def make_payment(self, method=None, phone=None):
        if not flt(self.agreed_price):
            frappe.throw(_("A fare must be agreed before paying for this trip."),
                         title=_("No Agreed Fare"))
        if self.workflow_state not in ("PRICE_AGREED", "ACCEPTED", "PENDING"):
            frappe.throw(_("This trip cannot be paid in its current state."),
                         title=_("Wrong State"))
        return super().make_payment(method=method, phone=phone)

    # -- execution (SRS 3.3 step 6) --------------------------------------
    def start_trip(self):
        """Driver begins the route -> PICKED_UP ("Route Active")."""
        state_machine.set_state(self, "PICKED_UP", note=_("Route active"))
        self.save(ignore_permissions=True)
        return self

    def advance_stop(self, stop_index=None, note=None):
        """Mark the next stop reached and return the itinerary progress."""
        stops = self.get("route_stops") or []
        if not stops:
            frappe.throw(_("This trip has no stops."), title=_("No Itinerary"))

        idx = int(flt(stop_index)) if stop_index else int(self.current_stop_index or 0)
        if idx < 1 or idx > len(stops):
            frappe.throw(_("Stop {0} is outside this itinerary (1-{1}).")
                         .format(idx, len(stops)), title=_("Invalid Stop"))

        stops[idx - 1].status = "Completed"
        self.current_stop_index = idx

        state_machine.append_history(
            self, self.workflow_state,
            note=_("Reached stop {0}/{1}: {2}").format(
                idx, len(stops), stops[idx - 1].address))
        self.save(ignore_permissions=True)

        remaining = len(stops) - idx
        if remaining <= 0:
            return self.complete_trip()

        return {"request": self.name, "stop": idx, "total_stops": len(stops),
                "remaining": remaining, "state": self.workflow_state}

    def complete_trip(self):
        for stop in (self.get("route_stops") or []):
            if stop.status != "Completed":
                stop.status = "Completed"
        self.current_stop_index = len(self.get("route_stops") or [])
        state_machine.set_state(self, "COMPLETED", note=_("Trip completed"))
        self.save(ignore_permissions=True)
        return self

    def reject_request(self, reason):
        if not reason:
            frappe.throw(_("A reason is required."), title=_("Reason Required"))
        self.negotiation_note = reason
        return self.cancel_document(reason)


def validate_request(doc, method=None):
    doc.validate()
