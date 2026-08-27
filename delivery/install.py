"""
Post-install setup for the Delivery & Logistics app.

Creates the actor roles from SRS section 2, the Logistics Settings singleton,
default weight categories, default zones and a demo catalogue so the platform
is usable the moment ``install-app`` finishes.
"""
import frappe
from frappe import _

ROLES = [
    ("Delivery Customer", _("Customer - browses catalogues, places orders, tracks state"), 0),
    ("Merchant User", _("Restaurant / Vendor - manages catalogue, accepts orders"), 0),
    ("Delivery Operations", _("Operations Staff - reviews requests, sets tariffs, assigns drivers"), 1),
    ("Driver", _("Driver / Courier - executes pickups and handoffs"), 0),
]

WEIGHT_CATEGORIES = [
    # name, min kg, max kg, base charge, per extra kg, priority
    ("Document / Envelope", 0, 0.5, 2500, 0, 10),
    ("Small Parcel", 0.5, 2, 3500, 250, 9),
    ("Medium Parcel", 2, 10, 5000, 300, 8),
    ("Large Parcel", 10, 25, 9000, 400, 7),
]

ZONES = [
    # name, city, base fee, per km, typical km, services
    ("Masaki", "Dar es Salaam", 2500, 600, 4, "Food, Retail, Parcel, Transport"),
    ("Mikocheni", "Dar es Salaam", 2000, 500, 6, "Food, Retail, Parcel, Transport"),
    ("Kariakoo", "Dar es Salaam", 1800, 450, 5, "Food, Retail, Parcel"),
    ("Upanga", "Dar es Salaam", 2000, 500, 5, "Food, Retail, Parcel, Transport"),
    ("Kinondoni", "Dar es Salaam", 2000, 500, 7, "Food, Retail, Parcel, Transport"),
    ("Ubungo", "Dar es Salaam", 2200, 550, 12, "Food, Retail, Parcel, Transport"),
    ("Mbezi", "Dar es Salaam", 2600, 650, 18, "Parcel, Transport"),
]


def after_install():
    create_roles()
    create_settings()
    create_weight_categories()
    create_zones()
    frappe.db.commit()
    frappe.clear_cache()
    print("Delivery & Logistics: roles, settings, weight categories and zones created.")


def create_roles():
    for name, desc, desk_access in ROLES:
        if not frappe.db.exists("Role", name):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": name,
                "desk_access": desk_access,
                "description": desc,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_settings():
    """
    Create the Logistics Settings singleton and pin the platform currency.

    ERPNext seeds a global default currency (INR on a stock install) which
    overrides a Currency *link* field's own default, so the currency is set
    explicitly here and committed.
    """
    if not frappe.db.exists("Logistics Settings", "Logistics Settings"):
        s = frappe.get_doc({
            "doctype": "Logistics Settings",
            "platform_name": "Swift Logistics",
            "enabled": 1,
            "currency": "TZS",
            "country": "Tanzania",
            "language": "en",
        })
        s.insert(ignore_permissions=True)
    else:
        s = frappe.get_doc("Logistics Settings", "Logistics Settings")
        if not s.currency:
            s.currency = "TZS"
            s.save(ignore_permissions=True)
    frappe.db.commit()


def create_weight_categories():
    for name, lo, hi, base, per_kg, prio in WEIGHT_CATEGORIES:
        if not frappe.db.exists("Parcel Weight Category", name):
            frappe.get_doc({
                "doctype": "Parcel Weight Category",
                "category_name": name,
                "min_weight_kg": lo,
                "max_weight_kg": hi,
                "base_charge": base,
                "per_kg_charge": per_kg,
                "priority": prio,
                "enabled": 1,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_zones():
    for name, city, base, per_km, dist, services in ZONES:
        if not frappe.db.exists("Delivery Zone", name):
            frappe.get_doc({
                "doctype": "Delivery Zone",
                "zone_name": name,
                "city": city,
                "base_fee": base,
                "per_km_fee": per_km,
                "distance_km": dist,
                "services": services,
                "enabled": 1,
            }).insert(ignore_permissions=True)
    frappe.db.commit()
