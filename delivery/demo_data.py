"""
Demo data for the Delivery & Logistics platform.

    bench --site <site> execute delivery.demo_data.seed
    bench --site <site> execute delivery.demo_data.reset

Every login shares ``PASSWORD``. Create these on a staging site only - the
passwords are published in the README.
"""
import frappe
from frappe import _
from frappe.utils import flt

PASSWORD = "Sw!ftLog1stics26"

USERS = [
    # email, first name, role, desk access
    ("customer@demo.test", "Amina", "Delivery Customer", 0),
    ("merchant@demo.test", "Juma", "Merchant User", 0),
    ("merchant2@demo.test", "Raj", "Merchant User", 0),
    ("merchant3@demo.test", "Grace", "Merchant User", 0),
    ("ops@demo.test", "Neema", "Delivery Operations", 1),
    ("driver@demo.test", "Baraka", "Driver", 0),
    ("driver2@demo.test", "Salim", "Driver", 0),
    ("driver3@demo.test", "Fatuma", "Driver", 0),
]

MERCHANTS = [
    {
        "merchant_id": "MRC-SWAHILI-GRILL",
        "merchant_name": "Swahili Grill House",
        "service_type": "Food",
        "portal_user": "merchant@demo.test",
        "phone": "+255700000001",
        "city": "Dar es Salaam", "area": "Masaki",
        "full_address": "Masaki Seafront, Dar es Salaam",
        "latitude": -6.7440, "longitude": 39.2780,
        "avg_prep_minutes": 25, "minimum_order_value": 10000,
        "delivery_radius_km": 8, "commission_rate": 15,
        "items": [
            # code, name, category, rate, prep min, stock
            ("SG-NYAMA-CHOMA", "Nyama Choma (500g)", "Grill", 18000, 30, 40),
            ("SG-PILAU", "Pilau Special", "Main", 12000, 20, 60),
            ("SG-UGALI-FISH", "Ugali & Fish", "Main", 14000, 25, 50),
            ("SG-CHIPS-MAYAI", "Chips Mayai", "Snacks", 7000, 15, 80),
            ("SG-MISHKAKI", "Mishkaki Skewers", "Grill", 9000, 20, 70),
            ("SG-CHAI", "Spiced Chai", "Drinks", 2000, 5, 200),
            ("SG-JUICE-AVOCADO", "Avocado Juice", "Drinks", 4500, 8, 120),
            ("SG-WALI-NDOVU", "Wali & Ndovu", "Main", 13000, 22, 45),
        ],
    },
    {
        "merchant_id": "MRC-KARIAKOO-MART",
        "merchant_name": "Kariakoo Mart",
        "service_type": "Retail",
        "portal_user": "merchant2@demo.test",
        "phone": "+255700000002",
        "city": "Dar es Salaam", "area": "Kariakoo",
        "full_address": "Mbezi Street, Kariakoo, Dar es Salaam",
        "latitude": -6.8210, "longitude": 39.2700,
        "avg_prep_minutes": 15, "minimum_order_value": 5000,
        "delivery_radius_km": 12, "commission_rate": 12,
        "items": [
            ("KM-RICE-5KG", "Rice 5kg", "Groceries", 15000, 10, 100),
            ("KM-SUGAR-2KG", "Sugar 2kg", "Groceries", 5000, 10, 150),
            ("KM-OIL-1L", "Cooking Oil 1L", "Groceries", 6500, 10, 120),
            ("KM-SOAP-PACK", "Soap Pack (6)", "Household", 9000, 10, 90),
            ("KM-MAIZE-10KG", "Maize Flour 10kg", "Groceries", 18000, 10, 70),
            ("KM-CHARCOAL", "Charcoal Sack", "Household", 25000, 15, 30),
            ("KM-SALT-1KG", "Salt 1kg", "Groceries", 1500, 10, 200),
            ("KM-TEA-500G", "Tea Leaves 500g", "Groceries", 8000, 10, 85),
        ],
    },
    {
        "merchant_id": "MRC-MASAKI-CAFE",
        "merchant_name": "Masaki Cafe",
        "service_type": "Food & Retail",
        "portal_user": "merchant3@demo.test",
        "phone": "+255700000003",
        "city": "Dar es Salaam", "area": "Masaki",
        "full_address": "Masaki Shopping Strip, Dar es Salaam",
        "latitude": -6.7460, "longitude": 39.2760,
        "avg_prep_minutes": 18, "minimum_order_value": 8000,
        "delivery_radius_km": 6, "commission_rate": 14,
        "items": [
            ("MC-COFFEE", "Single Origin Coffee", "Drinks", 6000, 6, 300),
            ("MC-CROISSANT", "Butter Croissant", "Bakery", 4000, 5, 60),
            ("MC-SANDWICH", "Grilled Chicken Sandwich", "Snacks", 11000, 12, 50),
            ("MC-SMOOTHIE", "Mango Smoothie", "Drinks", 7500, 7, 100),
            ("MC-SALAD", "Garden Salad", "Main", 12500, 10, 40),
            ("MC-BROWNIE", "Chocolate Brownie", "Bakery", 5000, 5, 70),
            ("MC-WRAP", "Beef Wrap", "Snacks", 10000, 12, 45),
            ("MC-WATER", "Bottled Water 500ml", "Drinks", 1000, 2, 400),
        ],
    },
]

DRIVERS = [
    {
        "driver_code": "DRV-001", "driver_name": "Baraka Mwangala",
        "user": "driver@demo.test", "phone": "+255711111111",
        "vehicle_type": "Motorcycle", "vehicle_plate": "T 123 ABC",
        "can_food": 1, "can_parcel": 1, "can_transport": 0,
        "max_load_kg": 20, "base_zone": "Masaki", "rating": 4.8,
    },
    {
        "driver_code": "DRV-002", "driver_name": "Salim Hassan",
        "user": "driver2@demo.test", "phone": "+255711111112",
        "vehicle_type": "Van", "vehicle_plate": "T 456 DEF",
        "can_food": 1, "can_parcel": 1, "can_transport": 1,
        "max_load_kg": 800, "base_zone": "Kinondoni", "rating": 4.6,
    },
    {
        "driver_code": "DRV-003", "driver_name": "Fatuma Juma",
        "user": "driver3@demo.test", "phone": "+255711111113",
        "vehicle_type": "Car", "vehicle_plate": "T 789 GHI",
        "can_food": 0, "can_parcel": 1, "can_transport": 1,
        "max_load_kg": 300, "base_zone": "Mikocheni", "rating": 4.9,
    },
]


# ---------------------------------------------------------------------------
def _make_user(email, first_name, role, desk_access):
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "send_welcome_email": 0,
            "user_type": "System User" if desk_access else "Website User",
        })
        user.append("roles", {"role": role})
        user.insert(ignore_permissions=True)

    user.new_password = PASSWORD
    user.save(ignore_permissions=True)
    frappe.db.commit()
    return user


def _make_merchant(spec):
    items = spec.pop("items")
    doc = frappe.get_doc(dict({"doctype": "Merchant", "status": "Open"}, **spec))
    doc.insert(ignore_permissions=True)

    for i, (code, name, category, rate, prep, stock) in enumerate(items, start=1):
        if frappe.db.exists("DL Menu Item", code):
            continue
        frappe.get_doc({
            "doctype": "DL Menu Item",
            "item_code": code,
            "item_name": name,
            "merchant": doc.name,
            "item_type": "Food" if spec["service_type"] != "Retail" else "Retail",
            "category": category,
            "standard_rate": flt(rate),
            "prep_minutes": prep,
            "available_stock": stock,
            "track_stock": 1,
            "published": 1,
            "is_featured": 1 if i <= 2 else 0,
        }).insert(ignore_permissions=True)

    spec["items"] = items
    frappe.db.commit()
    return doc


def _make_driver(spec):
    doc = frappe.get_doc(dict({"doctype": "Delivery Driver", "status": "Available"}, **spec))
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def seed():
    """Idempotently create demo users, merchants, catalogue and drivers."""
    for email, first, role, desk in USERS:
        _make_user(email, first, role, desk)

    merchants = [_make_merchant(dict(m)) for m in MERCHANTS]
    drivers = [_make_driver(dict(d)) for d in DRIVERS]

    frappe.db.commit()
    print("Seeded: {0} merchants, {1} menu items, {2} drivers. Password: {3}".format(
        len(merchants),
        frappe.db.count("DL Menu Item"),
        len(drivers), PASSWORD))
    return {"merchants": [m.name for m in merchants],
            "drivers": [d.name for d in drivers]}


def reset():
    """Remove demo transactions and master data (keeps roles, zones, bands)."""
    for dt in ("Payment Transaction", "Dispatch Trip", "Delivery Order",
               "Parcel Request", "Transport Request", "DL Menu Item",
               "Delivery Driver", "Merchant"):
        for name in frappe.get_all(dt, pluck="name", limit=5000):
            frappe.delete_doc(dt, name, ignore_permissions=True, force=True)

    for email, _, _, _ in USERS:
        if frappe.db.exists("User", email):
            frappe.delete_doc("User", email, ignore_permissions=True, force=True)

    frappe.db.commit()
    print("Demo data cleared.")
    return True


# ---------------------------------------------------------------------------
# Live-tracking demo: fake driver movement on the /delivery/track Leaflet map
# ---------------------------------------------------------------------------
# A demo route across Dar es Salaam: pickup near Kariakoo (-6.821, 39.270)
# heading toward Masaki peninsula (-6.742, 39.275).
_ORIGIN = (-6.8210, 39.2700)
_DEST = (-6.7420, 39.2750)
_HOPS = 25


def _ping(reference, driver, lat, lng, activity="On Trip"):
	import datetime
	log = frappe.new_doc("Driver Location Log")
	log.driver = driver
	log.reference = reference or ""
	log.activity = activity
	log.latitude = lat
	log.longitude = lng
	log.accuracy = 12.0
	log.timestamp = frappe.utils.now()
	log.flags.ignore_mandatory = True
	log.insert(ignore_permissions=True)
	frappe.db.set_value("Delivery Driver", driver,
	                    {"latitude": lat, "longitude": lng}, update_modified=False)
	return log


@frappe.whitelist()
def simulate_move(reference=None, hops=_HOPS, activity="On Trip"):
	"""
	Generate GPS pings so the customer's tracking map shows driver movement.

	- ``simulate_move(reference="DL-ORD-2026-0001")`` draws the WHOLE route at
	  once (for an instant demo / screenshot).
	- call it repeatedly (bench console loop) to advance the driver one hop at
	  a time so the live map visibly moves.

	Requires System Manager / administrator (it is demo tooling, not a public API).
	"""
	# guard: only back-office admins may fabricate GPS pings
	roles = set(frappe.get_roles(frappe.session.user))
	if frappe.session.user != "Administrator" and "System Manager" not in roles:
		frappe.throw("Not allowed.", frappe.PermissionError)

	# resolve driver: from the order, else the first demo driver (Baraka)
	driver = None
	if reference:
		for dt in ("Delivery Order", "Parcel Request", "Transport Request"):
			if frappe.db.exists(dt, reference):
				driver = frappe.db.get_value(dt, reference, "assigned_driver")
				break
	if not driver:
		driver = frappe.db.get_value("Delivery Driver",
		                             {"driver_code": "DRV-001"}, "name") \
		         or frappe.db.get_value("Delivery Driver",
		                               {"name": ("!=", "")}, "name",
		                               order_by="creation asc")
	if not driver:
		frappe.throw("No driver found to simulate.")

	# how far along the route this driver already is
	done = frappe.db.count("Driver Location Log", {"driver": driver})
	import random
	lat0, lng0 = _ORIGIN
	lat1, lng1 = _DEST
	step = max(done, 0)
	made = []
	for _ in range(int(hops)):
		if step >= _HOPS:
			break
		frac = step / float(_HOPS)
		lat = lat0 + (lat1 - lat0) * frac + random.uniform(-0.0006, 0.0006)
		lng = lng0 + (lng1 - lng0) * frac + random.uniform(-0.0006, 0.0006)
		made.append(_ping(reference, driver, round(lat, 6), round(lng, 6), activity).name)
		step += 1

	frappe.db.commit()
	progress = min(step, _HOPS)
	print("Driver {0}: {1}/{2} route points ({3} new) for {4}".format(
		driver, progress, _HOPS, len(made), reference or "(no ref)"))
	return {"driver": driver, "progress": progress, "total": _HOPS,
	        "created": len(made), "arrived": progress >= _HOPS}


@frappe.whitelist()
def simulate_reset(driver=None):
	"""Delete demo Driver Location Log rows (fresh re-run of the route)."""
	roles = set(frappe.get_roles(frappe.session.user))
	if frappe.session.user != "Administrator" and "System Manager" not in roles:
		frappe.throw("Not allowed.", frappe.PermissionError)
	for name in frappe.get_all("Driver Location Log", pluck="name", limit=100000):
		frappe.delete_doc("Driver Location Log", name, ignore_permissions=True, force=True)
	frappe.db.commit()
	print("Driver Location Log cleared.")
	return True
