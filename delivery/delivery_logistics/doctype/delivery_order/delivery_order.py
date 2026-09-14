"""Delivery Order - Food and Retail service (SRS 3.1)."""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime, add_to_date

from delivery.delivery_logistics import billing, payments, state_machine
from delivery.delivery_logistics.base import ServiceDocument


class DeliveryOrder(ServiceDocument):
    AMOUNT_FIELD = "grand_total"

    #: the ONLY move a merchant may make on workflow_state from Desk
    MERCHANT_STATE_MOVES = (("ACCEPTED", "READY_FOR_DELIVERY"),
                            ("PREPARING", "READY_FOR_DELIVERY"))

    def service(self):
        return self.get("order_type") or "Food"

    def _guard_merchant_state_change(self):
        """Merchants may set Workflow State to READY_FOR_DELIVERY (so ops can
        dispatch); every other state change stays admin/ops-only."""
        roles = set(frappe.get_roles())
        if {"System Manager", "Delivery Operations"} & roles:
            return
        if "Merchant User" not in roles:
            return
        if self.is_new() or not self.get("workflow_state"):
            return
        old = frappe.db.get_value("Delivery Order", self.name, "workflow_state")
        if not old or old == self.workflow_state:
            return
        if (old, self.workflow_state) not in self.MERCHANT_STATE_MOVES:
            frappe.throw(_("Merchants can only move an accepted/preparing order "
                           "to READY FOR DELIVERY."), frappe.PermissionError)
        # route through the state machine so the audit trail is written
        self.workflow_state = old
        state_machine.set_state(self, "READY_FOR_DELIVERY",
                                note=_("Merchant marked the order ready for delivery"))

    # -- lifecycle --------------------------------------------------------
    def validate(self):
        self._guard_merchant_state_change()

        # Stock is only drawn down once, when the order is first created.
        billing.food_retail_totals(self, adjust_stock=self.is_new())

        if not self.get("merchant_name_f") and self.get("merchant"):
            self.merchant_name_f = frappe.db.get_value(
                "Merchant", self.merchant, "merchant_name")

        if not self.get("payment_status"):
            self.payment_status = "Pending"

        if not self.get("workflow_state"):
            state_machine.set_state(
                self, state_machine.SERVICE_ENTRY[self.service()],
                note=_("Order placed"))

        if not self.get("otp_code"):
            self.otp_code = state_machine._new_otp()

    # -- merchant side ----------------------------------------------------
    def submit_for_merchant(self):
        """SRS 3.1 step 2 - order lands in the Merchant portal awaiting acceptance."""
        if self.workflow_state != "PENDING":
            state_machine.set_state(self, "PENDING", note=_("Awaiting merchant"))
            self.save(ignore_permissions=True)
        return self

    def accept_order(self, prep_minutes=None):
        """
        SRS 3.1 step 3 - merchant confirms and the prep timer starts.

        Acceptance moves PENDING -> ACCEPTED and, because the kitchen/packing
        starts immediately, on to PREPARING with ``ready_at`` set.
        """
        if self.workflow_state not in ("PENDING", "ACCEPTED"):
            frappe.throw(_("Only a pending order can be accepted."),
                         title=_("Wrong State"))

        prep = int(flt(prep_minutes) or self.get("prep_minutes")
                   or int(billing._cfg("default_prep_minutes") or 30))
        self.prep_minutes = prep

        state_machine.set_state(self, "ACCEPTED", note=_("Merchant accepted"))
        self.ready_at = add_to_date(now_datetime(), minutes=prep)
        state_machine.set_state(self, "PREPARING",
                                note=_("Preparation started ({0} min)").format(prep))
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self

    def reject_order(self, reason):
        if not reason:
            frappe.throw(_("A rejection reason is required."),
                         title=_("Reason Required"))
        state_machine.set_state(self, "CANCELLED",
                                note=_("Merchant rejected: {0}").format(reason))
        self.cancellation_reason = reason
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self

    def mark_ready_for_delivery(self, note=None):
        """Merchant signals the order is ready (ACCEPTED/PREPARING ->
        READY_FOR_DELIVERY). Operations then assigns a driver."""
        if self.workflow_state not in ("ACCEPTED", "PREPARING"):
            frappe.throw(_("Only an accepted/preparing order can be marked ready "
                           "(currently {0}).").format(self.workflow_state),
                         title=_("Wrong State"))
        state_machine.set_state(self, "READY_FOR_DELIVERY",
                                note=note or _("Merchant marked the order ready for delivery"))
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self


# ---------------------------------------------------------------------------
# module-level hooks kept for compatibility; the Document methods above are what
# actually run (hooks.doc_events is intentionally not wired to avoid the
# validate pass firing twice and drawing down stock twice).
# ---------------------------------------------------------------------------
def validate_order(doc, method=None):
    doc.validate()


def on_update_order(doc, method=None):
    pass


def on_submit_order(doc, method=None):
    pass
