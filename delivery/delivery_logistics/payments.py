"""
Payment gateways for the platform - SRS section 3.4.

Two families:

* **Cash On Delivery** - no gateway. A Payment Transaction is still created so
  the driver has a remittance record; it settles to ``Paid`` at handoff.
* **Mobile money / card** - M-Pesa, Tigo Pesa and Card, each behind a small
  adapter interface so a real integration can be dropped in without touching
  any calling code.

``Logistics Settings.simulate_payment_gateways`` routes every call to an
in-process simulator, which is what makes the whole flow testable with no
credentials. When it is off and no real adapter is registered, the call
**refuses** rather than pretending a charge went through.
"""
import json
import random
import string
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

COD = "Cash On Delivery"
MPESA = "M-Pesa"
TIGO_PESA = "Tigo Pesa"
CARD = "Card"

ALL_METHODS = [COD, MPESA, TIGO_PESA, CARD]


def settings():
    from delivery.delivery_logistics.billing import settings as _s
    return _s()


def _flag(field):
    try:
        return bool(settings().get(field))
    except Exception:
        return False


def enabled_methods():
    """Methods switched on in Logistics Settings, COD first."""
    out = []
    if _flag("cod_enabled"):
        out.append(COD)
    if _flag("mpesa_enabled"):
        out.append(MPESA)
    if _flag("tigo_pesa_enabled"):
        out.append(TIGO_PESA)
    if _flag("card_enabled"):
        out.append(CARD)
    return out or [COD]


def simulate():
    return _flag("simulate_payment_gateways")


# ---------------------------------------------------------------------------
# gateway registry
# ---------------------------------------------------------------------------
def _sim_reference(method):
    """Sandbox-shaped reference, e.g. SIMMPESR79YXVVXCK."""
    tag = {MPESA: "MPES", TIGO_PESA: "TIGO", CARD: "CARD"}.get(method, "GEN")
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    return "SIM{0}{1}".format(tag, rand)


def _simulate_charge(method, amount, currency, phone=None):
    """
    In-process gateway. Always succeeds, always labelled as a simulation so a
    sandbox reference can never be mistaken for a real settlement.
    """
    if method in (MPESA, TIGO_PESA) and not phone:
        return False, {"error": _("A mobile money number is required.")}
    return True, {
        "simulated": True,
        "gateway": method,
        "transaction_id": _sim_reference(method),
        "amount": flt(amount),
        "currency": currency,
        "phone": phone,
        "status": "SUCCESS",
        "processed_at": now_datetime().isoformat(),
    }


#: Register real adapters here: {"M-Pesa": my_module.charge}
#: An adapter takes (amount, currency, phone=None) and returns (ok, response).
ADAPTERS = {}


def _charge(method, amount, currency, phone=None):
    if simulate():
        return _simulate_charge(method, amount, currency, phone)

    adapter = ADAPTERS.get(method)
    if not adapter:
        frappe.throw(
            _("No live adapter is registered for {0}, and gateway simulation is "
              "turned off. Refusing to record a payment that did not happen.")
            .format(method),
            title=_("Gateway Not Configured"),
        )
    return adapter(amount, currency, phone=phone)


# ---------------------------------------------------------------------------
# Payment Transaction records
# ---------------------------------------------------------------------------
def record(reference_doctype, reference_name, method, amount, currency,
           status="Pending", gateway=None, transaction_id=None, phone=None,
           raw=None, collected_amount=None, change_due=None,
           failure_reason=None):
    txn = frappe.get_doc({
        "doctype": "Payment Transaction",
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "payment_method": method,
        "payment_status": status,
        "amount": flt(amount),
        "currency": currency,
        "gateway": gateway,
        "transaction_id": transaction_id,
        "phone": phone,
        "raw_response": json.dumps(raw, indent=1, default=str) if raw else None,
        "collected_amount": flt(collected_amount) if collected_amount else 0,
        "change_due": flt(change_due) if change_due else 0,
        "paid_on": now_datetime() if status == "Paid" else None,
        "failure_reason": failure_reason,
    })
    txn.insert(ignore_permissions=True)
    return txn


def pay_now(reference_doctype, reference_name, method, amount, currency,
            phone=None):
    """
    Charge immediately (mobile money / card) and return ``(txn, payload)``.

    COD is not charged here - see :func:`open_cod`.
    """
    if method == COD:
        return open_cod(reference_doctype, reference_name, amount, currency), {}

    if method not in enabled_methods():
        frappe.throw(_("{0} is not an available payment method.").format(method),
                     title=_("Payment Method Unavailable"))

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Nothing to pay."), title=_("Invalid Amount"))

    ok, response = _charge(method, amount, currency, phone=phone)
    status = "Paid" if ok else "Failed"

    txn = record(reference_doctype, reference_name, method, amount, currency,
                 status=status, gateway=method,
                 transaction_id=response.get("transaction_id"),
                 phone=phone, raw=response,
                 failure_reason=None if ok else str(response.get("error"))[:140])
    return txn, response


def open_cod(reference_doctype, reference_name, amount, currency):
    """
    Create the remittance record for a Cash On Delivery job.

    The SRS treats COD as a real payment leg: the driver collects it at handoff,
    so it needs a transaction to settle against.
    """
    return record(reference_doctype, reference_name, COD, amount, currency,
                  status="Pending", gateway="COD")


def settle_cod(txn, collected_amount):
    """Driver hands over the cash - close out the COD transaction."""
    collected = flt(collected_amount)
    due = flt(txn.amount)

    if collected <= 0:
        frappe.throw(_("Enter the amount actually collected."),
                     title=_("Invalid Amount"))

    txn.collected_amount = collected
    txn.change_due = max(0.0, round(collected - due, 2))
    txn.payment_status = "Paid"
    txn.paid_on = now_datetime()
    txn.gateway = "COD"
    txn.raw_response = json.dumps({
        "settled_by": frappe.session.user,
        "collected": collected,
        "due": due,
        "at": str(now_datetime()),
    }, indent=1, default=str)
    txn.save(ignore_permissions=True)
    return txn


def current_txn(reference_doctype, reference_name):
    """Most recent transaction for a document, if any."""
    name = frappe.db.get_value(
        "Payment Transaction",
        {"reference_doctype": reference_doctype, "reference_name": reference_name},
        "name", order_by="creation desc")
    return frappe.get_doc("Payment Transaction", name) if name else None
