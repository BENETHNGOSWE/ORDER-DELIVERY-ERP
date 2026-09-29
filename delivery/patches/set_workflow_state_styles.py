"""
Give every Delivery Order workflow state a colour so the Desk list view
(and the form sidebar badge) differentiates states at a glance.

Frappe's Desk list renders the Workflow State column from the Workflow
State master's ``style`` field - states without a style all fall back to
grey, which made the orders list impossible to scan.

Style -> badge colour mapping used by Desk:
    Success = green   Warning = orange   Danger  = red
    Primary = blue    Info    = light-blue   Inverse = grey
"""
import frappe

# urgency language (matches the portal: yellow/attention, red/urgent)
STYLES = {
    "REQUESTED": "Inverse",
    "UNDER_REVIEW": "Info",
    "PRICE_AGREED": "Primary",
    "PENDING": "Warning",            # merchant must accept -> orange
    "ACCEPTED": "Info",
    "PREPARING": "Primary",
    "READY_FOR_DELIVERY": "Danger",  # needs a driver -> red
    "DRIVER_ASSIGNED": "Primary",
    "PICKED_UP": "Info",
    "COMPLETED": "Success",
    "CANCELLED": "Inverse",
}


def execute():
    # every state we know + any state actually wired on a Delivery Order workflow
    names = set(STYLES)
    for wf in frappe.get_all("Workflow",
                             filters={"document_type": "Delivery Order"},
                             pluck="name"):
        for s in frappe.get_all("Workflow Document State",
                                filters={"parent": wf, "parenttype": "Workflow"},
                                pluck="state"):
            names.add(s)

    for name in names:
        style = STYLES.get(name, "Primary")  # unknown states -> blue, never grey
        if frappe.db.exists("Workflow State", name):
            frappe.db.set_value("Workflow State", name, "style", style)
        else:
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": name,
                "style": style,
            }).insert(ignore_permissions=True)

    frappe.clear_cache()
    print("Delivery: workflow state colours set for {0} states.".format(len(names)))
