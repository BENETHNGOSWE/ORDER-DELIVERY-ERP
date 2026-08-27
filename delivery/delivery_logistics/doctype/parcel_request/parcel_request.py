"""Parcel Request - point-to-point parcel delivery (SRS 3.2)."""
import frappe
from frappe import _
from frappe.utils import flt

from delivery.delivery_logistics import billing, state_machine
from delivery.delivery_logistics.base import ServiceDocument


class ParcelRequest(ServiceDocument):
    SERVICE = "Parcel"
    AMOUNT_FIELD = "tariff_amount"

    def validate(self):
        billing.apply_currency(self)

        needs_review, totals = billing.parcel_billing(self)
        self._needs_review = needs_review

        if not self.get("payment_status"):
            self.payment_status = "Pending"
        if not self.get("otp_code"):
            self.otp_code = state_machine._new_otp()

        if not self.get("workflow_state"):
            # SRS 3.2: a matching weight category bills instantly; anything
            # heavy, oversized or uncategorised goes to a manual quote.
            state_machine.set_state(self, "REQUESTED", note=_("Details submitted"))
            if needs_review:
                state_machine.set_state(
                    self, "UNDER_REVIEW",
                    note=_("Custom tariff required - awaiting operations"))
            else:
                state_machine.set_state(
                    self, "PRICE_AGREED",
                    note=_("Instant tariff {0}").format(totals.get("tariff_amount")))

    # -- operations side --------------------------------------------------
    def set_tariff(self, amount, note=None):
        """Operations agrees the tariff for a parcel in manual review."""
        if self.workflow_state not in ("UNDER_REVIEW", "REQUESTED", "PRICE_AGREED"):
            frappe.throw(_("A tariff can only be set before the parcel is accepted."),
                         title=_("Wrong State"))

        billing.set_manual_tariff(self, amount, note)
        self.review_note = note
        state_machine.set_state(self, "PRICE_AGREED",
                                note=_("Tariff agreed: {0}").format(flt(amount)))
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return self

    def reject_parcel(self, reason):
        if not reason:
            frappe.throw(_("A reason is required."), title=_("Reason Required"))
        self.review_note = reason
        return self.cancel_document(reason)


def validate_parcel(doc, method=None):
    doc.validate()
