"""
Map legacy Merchant.service_type values onto the full category list.

Old options were Food / Retail / Food & Retail; the platform now runs
six categories (Food, Groceries, Drinks, Pharmacy & Cosmetics,
Shopping, Others) - Category -> Merchants -> Merchant Products.

    Retail        -> Groceries   (retail merchants sold day-to-day goods)
    Grocery       -> Groceries
    Food & Retail -> Food        (they already appeared under Restaurant)
    Restaurant    -> Food
"""
import frappe

MAP = {
    "Retail": "Groceries",
    "Grocery": "Groceries",
    "Food & Retail": "Food",
    "Restaurant": "Food",
}


def execute():
    moved = 0
    for old, new in MAP.items():
        names = frappe.get_all("Merchant", filters={"service_type": old}, pluck="name")
        for n in names:
            frappe.db.set_value("Merchant", n, "service_type", new,
                                update_modified=False)
        moved += len(names)
    if moved:
        frappe.db.commit()
    print("Delivery: {0} merchant(s) moved to the new service types.".format(moved))
