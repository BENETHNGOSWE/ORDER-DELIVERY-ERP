"""
Shared behaviour for the three service documents.

Delivery Order, Parcel Request and Transport Request all need the same
tracking / payment / dispatch / handoff verbs. They live here once so the three
controllers stay thin and cannot drift apart.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from delivery.delivery_logistics import billing, payments, state_machine


class ServiceDocument(Document):
    """Mixin providing the common service-document verbs."""

    SERVICE = "Food"
    #: field holding the amount payable
    AMOUNT_FIELD = "grand_total"

    # -- state ------------------------------------------------------------
    def service(self):
        return state_machine.service_of(self)

    def _set(self, target, note=None, commit=False):
        """Transition + persist. The only way state changes here."""
        state_machine.set_state(self, target, note=note)
        self.save(ignore_permissions=True)
        if commit:
            frappe.db.commit()
        return self

    def state_label(self):
        return state_machine.label_for(self, self.workflow_state)

    # -- tracking ---------------------------------------------------------
    def get_tracking(self):
        """
        Public tracking payload (SRS 2 - Track Order Status).

        ``/track`` is guest-accessible, so the handoff OTP is only included for
        the customer who owns the document (or Operations).
        """
        user = frappe.session.user
        privileged = (user == self.get("customer")
                      or user == "Administrator"
                      or bool({"System Manager", "Delivery Operations"}
                              & set(frappe.get_roles())))

        data = {
            "reference": self.name,
            "service": self.service(),
            "state": self.workflow_state,
            "label": self.state_label(),
            "timeline": state_machine.timeline(self),
            "currency": self.get("currency") or billing._currency(),
            "amount": flt(self.get(self.AMOUNT_FIELD), 2),
            "payment_status": self.get("payment_status"),
            "payment_method": self.get("payment_method"),
            "driver": self.get("assigned_driver"),
            "driver_name": frappe.db.get_value("Delivery Driver",
                                               self.get("assigned_driver"),
                                               "driver_name"),
            "picked_up_at": str(self.get("picked_up_at") or ""),
            "completed_at": str(self.get("completed_at") or ""),
        }
        if privileged:
            data["otp_code"] = self.get("otp_code")
        return data

    # -- payment ----------------------------------------------------------
    def make_payment(self, method=None, phone=None):
        method = method or self.get("payment_method") or payments.COD

        if method not in payments.enabled_methods():
            frappe.throw(_("{0} is not an available payment method.").format(method),
                         title=_("Payment Method Unavailable"))

        amount = flt(self.get(self.AMOUNT_FIELD))
        if amount <= 0:
            frappe.throw(_("There is nothing to pay on {0}.").format(self.name),
                         title=_("Nothing To Pay"))

        self.payment_method = method
        txn, response = payments.pay_now(self.doctype, self.name, method, amount,
                                         self.get("currency"), phone=phone)
        self.payment_transaction = txn.name
        self.payment_status = txn.payment_status
        self.save(ignore_permissions=True)

        # a successful prepaid leg confirms the job
        if txn.payment_status == "Paid" and self.workflow_state in (
                "PENDING", "PRICE_AGREED"):
            state_machine.set_state(self, "ACCEPTED", note=_("Payment received"))
            self.save(ignore_permissions=True)

        return {"reference": self.name, "state": self.workflow_state,
                "payment_status": txn.payment_status,
                "transaction": txn.transaction_id or txn.name,
                "amount": amount, "currency": self.get("currency")}

    # -- cancellation -----------------------------------------------------
    def cancel_document(self, reason):
        if not reason:
            frappe.throw(_("A cancellation reason is required."),
                         title=_("Reason Required"))
        if self.workflow_state in state_machine.TERMINAL:
            frappe.throw(_("{0} is already {1}.").format(
                self.name, self.workflow_state), title=_("Already Closed"))

        self.cancellation_reason = reason
        state_machine.set_state(self, "CANCELLED", note=reason)
        self.save(ignore_permissions=True)
        return self

    # -- dispatch ---------------------------------------------------------
    def assign_driver(self, driver, trip=None):
        if not frappe.db.exists("Delivery Driver", driver):
            frappe.throw(_("Unknown driver: {0}").format(driver),
                         frappe.DoesNotExistError)

        self.assigned_driver = driver
        if trip:
            self.dispatch_trip = trip

        # OTP is issued when a driver takes the job (SRS 3.1 step 5)
        state_machine.set_state(self, "DRIVER_ASSIGNED",
                                note=_("Assigned to {0}").format(driver))
        self.save(ignore_permissions=True)

        frappe.db.set_value("Delivery Driver", driver, "status", "On Trip")
        return self

    def confirm_pickup(self):
        if not self.get("assigned_driver"):
            frappe.throw(_("No driver is assigned to {0} yet.").format(self.name),
                         title=_("No Driver"))
        state_machine.set_state(self, "PICKED_UP", note=_("Collected"))
        self.save(ignore_permissions=True)
        return self

    def complete_handoff(self, otp=None, collected_amount=0):
        """
        Proof of delivery (SRS 3.1 step 5).

        The customer's 4-digit code must match, and a Cash On Delivery job
        settles its Payment Transaction here so the driver's remittance is
        recorded against the handoff.
        """
        expected = self.get("otp_code")
        if expected and str(otp or "").strip() != str(expected):
            frappe.throw(
                _("Incorrect handoff OTP. Ask the customer for the 4-digit code."),
                title=_("OTP Mismatch"))

        if self.get("payment_method") == payments.COD:
            txn = (frappe.get_doc("Payment Transaction", self.payment_transaction)
                   if self.get("payment_transaction")
                   else payments.current_txn(self.doctype, self.name))
            if txn and txn.payment_status != "Paid":
                payments.settle_cod(txn, flt(collected_amount)
                                    or flt(self.get(self.AMOUNT_FIELD)))
                self.payment_transaction = txn.name
                self.payment_status = "Paid"

        state_machine.set_state(self, "COMPLETED", note=_("Delivered"))
        self.save(ignore_permissions=True)
        return self
