import frappe
from frappe.model.document import Document


class DLMenuItem(Document):
    def validate(self):
        """Desk guard for merchant-created items: stamp the merchant's own
        Merchant record on create, and never let a merchant touch another
        merchant's item. Ops/admin are unrestricted. (The merchant web portal
        already passes its own merchant; this keeps Desk consistent.)"""
        roles = set(frappe.get_roles())
        if {"System Manager", "Delivery Operations"} & roles:
            return
        if "Merchant User" not in roles:
            return
        mine = frappe.get_all("Merchant", filters={"portal_user": frappe.session.user},
                              pluck="name")
        if not mine:
            frappe.throw("Your login is not linked to a merchant profile.",
                         frappe.PermissionError)
        if not self.merchant:
            self.merchant = mine[0]
        elif self.merchant not in mine:
            frappe.throw("You can only manage your own menu items.",
                         frappe.PermissionError)
