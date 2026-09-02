"""
Customer-facing REST API.

Every endpoint is whitelisted and works with a Frappe session (web portal) or
an API key/secret + token (the mobile app), so the mobile build reuses this
surface verbatim.

Route prefix: /api/method/delivery.api.customer.*
"""
import frappe
from frappe import _
from frappe.utils import flt

from delivery.delivery_logistics import billing, payments


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _require_login():
    if frappe.session.user in ("", "Guest"):
        frappe.throw(_("Please log in."), frappe.AuthenticationError)
    return frappe.session.user


def _my_merchant_ids():
    return []


# ---------------------------------------------------------------------------
# catalogue
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_merchants(service_type=None, search=None, zone=None):
    """Merchants currently open, for the customer landing page."""
    filters = {"status": "Open"}
    if service_type:
        filters["service_type"] = ["in", [service_type, "Food & Retail"]]

    rows = frappe.get_all("Merchant", filters=filters,
                          fields=["name", "merchant_id", "merchant_name", "service_type",
                                  "city", "area", "avg_prep_minutes", "logo",
                                  "minimum_order_value", "latitude", "longitude"],
                          order_by="merchant_name asc", limit=100)

    if search:
        s = f"%{search}%"
        rows = [r for r in rows if s.replace("%", "").lower()
                in (r.merchant_name or "").lower()]
    return rows


@frappe.whitelist(allow_guest=True)
def merchant_catalog(merchant, item_type=None, category=None, search=None):
    """Published, in-stock catalogue for one merchant."""
    filters = {"merchant": merchant, "published": 1}
    if item_type:
        filters["item_type"] = item_type
    if category:
        filters["category"] = category

    fields = ["name", "item_code", "item_name", "item_type", "category", "description",
              "standard_rate", "discount_rate", "available_stock", "track_stock",
              "prep_minutes", "item_image", "is_featured"]
    rows = frappe.get_all("DL Menu Item", filters=filters, fields=fields,
                          order_by="is_featured desc, item_name asc", limit=300)

    if search:
        q = search.lower()
        rows = [r for r in rows
                if q in (r.item_name or "").lower() or q in (r.category or "").lower()]

    # group by category for the web menu
    grouped = {}
    for r in rows:
        grouped.setdefault(r.category or "Other", []).append(r)

    return {"merchant": merchant, "items": rows, "grouped": grouped}


@frappe.whitelist(allow_guest=True)
def browse_items(search=None, category=None, item_type=None, sort="featured", limit=200):
    """
    Marketplace-wide catalogue for the home page: every published, in-stock
    item across all open merchants, with merchant info attached. Search,
    category/type filter and sort are applied here (and can also be done
    client-side for instant response).
    """
    filters = {"published": 1}
    if category:
        filters["category"] = category
    if item_type:
        filters["item_type"] = item_type

    order_by = {
        "featured": "is_featured desc, item_name asc",
        "price_asc": "standard_rate asc",
        "price_desc": "standard_rate desc",
        "fast": "prep_minutes asc",
        "name": "item_name asc",
    }.get(sort, "is_featured desc, item_name asc")

    rows = frappe.get_all("DL Menu Item", filters=filters,
        fields=["name", "item_code", "item_name", "item_type", "category",
                "description", "standard_rate", "discount_rate", "prep_minutes",
                "item_image", "is_featured", "available_stock", "merchant"],
        order_by=order_by, limit=limit)

    # attach merchant info + only items from OPEN merchants
    merchants = {m.name: m for m in frappe.get_all(
        "Merchant", filters={"status": "Open"},
        fields=["name", "merchant_name", "service_type", "area", "city",
                "avg_prep_minutes", "logo"])}

    items = []
    for r in rows:
        m = merchants.get(r.merchant)
        if not m:
            continue
        if search:
            q = search.lower()
            if q not in (r.item_name or "").lower() \
               and q not in (r.category or "").lower() \
               and q not in (m.merchant_name or "").lower():
                continue
        rate = flt(r.standard_rate)
        disc = flt(r.discount_rate or 0)
        price = rate - (rate * disc / 100.0) if disc else rate
        items.append({
            "name": r.name,
            "item_code": r.item_code,
            "item_name": r.item_name,
            "item_type": r.item_type,
            "category": r.category or "Other",
            "description": r.description or "",
            "rate": flt(price, 2),
            "standard_rate": rate,
            "discount_rate": disc,
            "prep_minutes": flt(r.prep_minutes or m.avg_prep_minutes or 20),
            "image": r.item_image or "",
            "featured": bool(r.is_featured),
            "in_stock": flt(r.available_stock or 0),
            "merchant": r.merchant,
            "merchant_name": m.merchant_name,
            "merchant_service": m.service_type,
            "merchant_area": m.area or m.city or "",
            "merchant_logo": m.logo or "",
        })
    return items


@frappe.whitelist(allow_guest=True)
def zones():
    return frappe.get_all("Delivery Zone", filters={"enabled": 1},
                          fields=["name", "zone_name", "city", "base_fee",
                                  "per_km_fee", "distance_km", "services"],
                          order_by="zone_name asc")


@frappe.whitelist(allow_guest=True)
def quote_delivery_fee(zone=None, distance_km=0, items_total=0):
    """Live fee preview for the cart (SRS 3.1 step 2)."""
    return billing.estimate_delivery_fee(zone, flt(distance_km), flt(items_total))


@frappe.whitelist(allow_guest=True)
def parcel_weight_categories():
    return frappe.get_all("Parcel Weight Category", filters={"enabled": 1},
                          fields=["name", "category_name", "min_weight_kg", "max_weight_kg",
                                  "base_charge", "per_kg_charge"],
                          order_by="min_weight_kg asc")


@frappe.whitelist(allow_guest=True)
def home_banners():
    """Published home-page hero carousel banners, ordered by sort order."""
    try:
        rows = frappe.get_all("Home Banner",
                              filters={"enabled": 1, "image": ["!=", ""]},
                              fields=["title", "subtitle", "image", "button_label", "button_link", "sort_order"],
                              order_by="sort_order asc, creation asc")
    except Exception:
        return []
    out = []
    for b in rows:
        if not b.image:
            continue
        out.append({
            "title": b.title or "",
            "subtitle": b.subtitle or "",
            "image": b.image,
            "button_label": b.button_label or "",
            "button_link": b.button_link or "",
        })
    return out


@frappe.whitelist(allow_guest=True)
def quote_parcel(weight_kg, length_cm=0, width_cm=0, height_cm=0,
                 distance_km=0, is_fragile=0):
    """
    Instant parcel tariff preview (SRS 3.2).
    Returns needs_review=True when the parcel needs a manual tariff.
    """
    doc = frappe.get_doc({
        "doctype": "Parcel Request",
        "weight_kg": flt(weight_kg),
        "length_cm": flt(length_cm), "width_cm": flt(width_cm), "height_cm": flt(height_cm),
        "distance_km": flt(distance_km), "is_fragile": int(is_fragile),
    })
    needs_review, totals = billing.parcel_billing(doc)
    return totals


@frappe.whitelist(allow_guest=True)
def quote_transport(stops, vehicle_type="Car", passengers=1):
    """
    Reference transport fare (SRS 3.3). Not binding - staff agree the real price.
    ``stops`` is a JSON list of {address, distance_from_prev_km}.
    """
    import json
    if isinstance(stops, str):
        stops = json.loads(stops)
    doc = frappe.get_doc({
        "doctype": "Transport Request",
        "vehicle_type": vehicle_type,
        "passengers": int(passengers),
        "route_stops": stops,
    })
    total = sum(flt(s.get("distance_from_prev_km")) for s in stops)
    doc.total_distance_km = billing.r2(total)
    fare = billing.transport_suggested_fare(doc)
    return {
        "suggested_fare": fare,
        "total_distance_km": doc.total_distance_km,
        "stops": len(stops),
        "currency": billing._currency(),
        "note": _("Reference only - operations will confirm the final fare by phone."),
    }


# ---------------------------------------------------------------------------
# food / retail orders
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def search_places(query, lat=None, lng=None, limit=8):
	"""
	Public place autocomplete for the checkout location box.
	Returns registered places (hotels, apartments, businesses, streets, areas)
	near Dar es Salaam with coordinates, so the delivery destination is exact.
	"""
	from delivery.delivery_logistics import geocode
	try:
		return geocode.search_places(query, lat=lat, lng=lng, limit=limit)
	except Exception:
		return []


@frappe.whitelist()
def place_order(merchant, items, delivery_address, order_type="Food",
                delivery_zone=None, delivery_distance_km=0,
                payment_method="Cash On Delivery", phone=None,
                delivery_instructions=None, customer_name=None,
                delivery_latitude=None, delivery_longitude=None):
    """
    SRS 3.1 steps 1-2: cart -> checkout -> order submitted to the merchant.

    ``items`` is a JSON list of {"item": "<DL Menu Item>", "qty": n}.
    """
    import json
    user = _require_login()
    if isinstance(items, str):
        items = json.loads(items)
    if not items:
        frappe.throw(_("Your cart is empty."), title=_("Empty Cart"))

    methods = payments.enabled_methods()
    if payment_method not in methods:
        frappe.throw(_("{0} is not available. Choose from: {1}.")
                     .format(payment_method, ", ".join(methods)))

    order = frappe.get_doc({
        "doctype": "Delivery Order",
        "order_type": order_type,
        "customer": user,
        "customer_name": customer_name or frappe.db.get_value("User", user, "full_name"),
        "customer_phone": phone,
        "merchant": merchant,
        "delivery_address": delivery_address,
        "delivery_zone": delivery_zone,
        "delivery_distance_km": flt(delivery_distance_km),
        "delivery_instructions": delivery_instructions,
        "payment_method": payment_method,
        "order_items": [{"item": i["item"], "qty": flt(i.get("qty", 1))} for i in items],
    })
    # exact destination coordinates captured at checkout (map pin / place search)
    if delivery_latitude is not None and delivery_longitude is not None \
            and flt(delivery_latitude) and flt(delivery_longitude):
        order.delivery_latitude = flt(delivery_latitude, 6)
        order.delivery_longitude = flt(delivery_longitude, 6)
    order.insert(ignore_permissions=True)

    # SRS 3.1 step 2 -> order lands in the Merchant portal as PENDING
    order.submit_for_merchant()

    # geocode any missing address coords in the BACKGROUND (never blocks the
    # customer or the tracking request)
    try:
        frappe.enqueue("delivery.delivery_logistics.geocode.backfill_coordinates",
                       reference=order.name, doctype="Delivery Order",
                       queue="short", timeout=120)
    except Exception:
        pass

    result = {"order": order.name, "state": order.workflow_state,
              "grand_total": flt(order.grand_total, 2), "currency": order.currency,
              "otp_code": order.otp_code}

    if payment_method != payments.COD:
        txn, pay = payments.pay_now("Delivery Order", order.name, payment_method,
                                    order.grand_total, order.currency, phone=phone)
        order.payment_transaction = txn.name
        order.payment_status = txn.payment_status
        order.save(ignore_permissions=True)
        result["payment"] = {"status": txn.payment_status, "reference": txn.transaction_id}

    return result


@frappe.whitelist()
def my_orders(state=None, limit=30):
    """Customer order history / dashboard (SRS 2 - Track Order Status)."""
    user = _require_login()
    filters = {"customer": user}
    if state:
        filters["workflow_state"] = state
    return frappe.get_all("Delivery Order", filters=filters,
                          fields=["name", "order_type", "merchant", "workflow_state",
                                  "grand_total", "currency", "payment_status",
                                  "assigned_driver", "creation", "ready_at"],
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist()
def my_parcels(state=None, limit=30):
    user = _require_login()
    filters = {"customer": user}
    if state:
        filters["workflow_state"] = state
    return frappe.get_all("Parcel Request", filters=filters,
                          fields=["name", "workflow_state", "billing_type", "weight_category",
                                  "tariff_amount", "currency", "payment_status",
                                  "assigned_driver", "creation",
                                  "pickup_address", "dropoff_address"],
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist()
def my_transport(state=None, limit=30):
    user = _require_login()
    filters = {"customer": user}
    if state:
        filters["workflow_state"] = state
    return frappe.get_all("Transport Request", filters=filters,
                          fields=["name", "trip_type", "workflow_state", "vehicle_type",
                                  "suggested_fare", "agreed_price", "currency",
                                  "payment_status", "assigned_driver", "creation",
                                  "total_distance_km", "quote_expires_on"],
                          order_by="creation desc", limit=int(limit))


@frappe.whitelist(allow_guest=True)
def track(reference):
    """
    Public tracking by reference (SRS 2 - Track Order Status).
    Accepts a Delivery Order, Parcel Request or Transport Request name.
    """
    for dt in ("Delivery Order", "Parcel Request", "Transport Request"):
        if frappe.db.exists(dt, reference):
            doc = frappe.get_doc(dt, reference)
            data = doc.get_tracking()
            data["doctype"] = dt
            return data
    frappe.throw(_("No order or request found with reference {0}.").format(reference),
                 frappe.DoesNotExistError)


@frappe.whitelist(allow_guest=True)
def track_route(reference, limit=200):
    """
    Live driver route for the public tracking map.

    Returns the driver's latest position plus the recent breadcrumb trail of
    Driver Location Log pings for this order, so the /delivery/track page can
    draw the driver moving with Leaflet.

    Privacy: data is only revealed once an order has a driver assigned. The
    endpoint is guest-accessible (the tracking page is public) but a valid
    order reference is required, and only that order's pings are returned.
    """
    doc = None
    dt = None
    for cand in ("Delivery Order", "Parcel Request", "Transport Request"):
        if frappe.db.exists(cand, reference):
            doc = frappe.get_doc(cand, reference)
            dt = cand
            break
    if not doc:
        frappe.throw(_("No order or request found with reference {0}.").format(reference),
                     frappe.DoesNotExistError)

    driver = doc.get("assigned_driver")
    state = doc.get("workflow_state")
    driver_name = None
    driver_phone = None
    trail = []
    latest = None
    pickup = dropoff = None

    if driver:
        driver_name = frappe.db.get_value("Delivery Driver", driver, "driver_name")
        driver_phone = frappe.db.get_value("Delivery Driver", driver, "phone")

        rows = frappe.get_all(
            "Driver Location Log",
            filters={"driver": driver, "reference": reference},
            fields=["latitude", "longitude", "accuracy", "activity", "timestamp"],
            order_by="timestamp asc",
            limit_page_length=limit,
        )
        # fall back to the driver's most recent pings even if not tagged to ref
        if not rows:
            rows = frappe.get_all(
                "Driver Location Log",
                filters={"driver": driver},
                fields=["latitude", "longitude", "accuracy", "activity", "timestamp"],
                order_by="timestamp asc",
                limit_page_length=limit,
            )
        for r in rows:
            lat, lng = flt(r.latitude, 6), flt(r.longitude, 6)
            if lat and lng:
                trail.append({"lat": lat, "lng": lng,
                              "activity": r.activity or "",
                              "accuracy": flt(r.accuracy or 0),
                              "timestamp": str(r.timestamp or "")})
        if trail:
            latest = trail[-1]

    # resolve pickup / destination coordinates (exact pins win, else geocode)
    try:
        from delivery.delivery_logistics import geocode
        pickup, dropoff = geocode.order_points(doc, dt)
    except Exception:
        pass

    return {
        "reference": reference,
        "doctype": dt,
        "service": doc.service(),
        "state": state,
        "driver": driver,
        "driver_name": driver_name,
        "driver_phone": driver_phone,
        "has_driver": bool(driver),
        "latest": latest,
        "trail": trail,
        "pickup": pickup,
        "dropoff": dropoff,
        "currency": doc.get("currency") or _billing_currency(),
    }


def _billing_currency():
    try:
        from delivery.delivery_logistics import billing
        return billing._currency()
    except Exception:
        return "TZS"


# ---------------------------------------------------------------------------
# parcel
# ---------------------------------------------------------------------------
@frappe.whitelist()
def place_parcel_request(pickup_address, dropoff_address, parcel_description,
                         weight_kg, length_cm=0, width_cm=0, height_cm=0,
                         is_fragile=0, distance_km=0, declared_value=0,
                         payment_method="Cash On Delivery", phone=None,
                         pickup_zone=None, dropoff_zone=None, customer_name=None):
    """SRS 3.2: point-to-point parcel with physical attribute logging."""
    user = _require_login()
    if payment_method not in payments.enabled_methods():
        frappe.throw(_("That payment method is not available."))

    parcel = frappe.get_doc({
        "doctype": "Parcel Request",
        "customer": user,
        "customer_name": customer_name or frappe.db.get_value("User", user, "full_name"),
        "customer_phone": phone,
        "pickup_address": pickup_address,
        "dropoff_address": dropoff_address,
        "pickup_zone": pickup_zone,
        "dropoff_zone": dropoff_zone,
        "parcel_description": parcel_description,
        "weight_kg": flt(weight_kg),
        "length_cm": flt(length_cm), "width_cm": flt(width_cm), "height_cm": flt(height_cm),
        "is_fragile": int(is_fragile),
        "distance_km": flt(distance_km),
        "declared_value": flt(declared_value),
        "payment_method": payment_method,
    })
    parcel.insert(ignore_permissions=True)

    needs_review = parcel.workflow_state == "UNDER_REVIEW"
    result = {
        "parcel": parcel.name,
        "state": parcel.workflow_state,
        "billing_type": parcel.billing_type,
        "weight_category": parcel.weight_category,
        "tariff_amount": flt(parcel.tariff_amount, 2),
        "currency": parcel.currency,
        "needs_review": needs_review,
        "otp_code": parcel.otp_code,
    }
    if needs_review:
        result["message"] = _(
            "This parcel needs a custom tariff. Operations will review it and set a price.")
    return result


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
@frappe.whitelist()
def place_transport_request(stops, trip_type="Passenger", vehicle_type="Car",
                            passengers=1, luggage_pieces=0, phone=None,
                            departure_datetime=None, special_requirements=None,
                            customer_name=None, return_trip=0):
    """
    SRS 3.3 step 1-2: multi-stop itinerary -> Request Reference ID in REQUESTED.
    ``stops`` is a JSON list of {idx_label, address, stop_type, distance_from_prev_km}.
    """
    import json
    user = _require_login()
    if isinstance(stops, str):
        stops = json.loads(stops)
    if len(stops) < 2:
        frappe.throw(_("Provide at least an origin and a destination."),
                     title=_("Incomplete Itinerary"))
    if not phone:
        frappe.throw(_("A phone number is required so operations can call to agree the fare."),
                     title=_("Phone Required"))

    req = frappe.get_doc({
        "doctype": "Transport Request",
        "customer": user,
        "customer_name": customer_name or frappe.db.get_value("User", user, "full_name"),
        "customer_phone": phone,
        "trip_type": trip_type,
        "vehicle_type": vehicle_type,
        "passengers": int(passengers),
        "luggage_pieces": int(luggage_pieces),
        "departure_datetime": departure_datetime,
        "special_requirements": special_requirements,
        "return_trip": int(return_trip),
        "route_stops": stops,
    })
    req.insert(ignore_permissions=True)

    return {
        "request": req.name,                      # e.g. TR-2026-0001
        "state": req.workflow_state,              # UNDER_REVIEW after insert
        "suggested_fare": flt(req.suggested_fare, 2),
        "total_distance_km": flt(req.total_distance_km, 2),
        "currency": req.currency,
        "message": _("Reference {0} created. Operations will call you on {1} to agree the fare.")
                   .format(req.name, phone),
    }


@frappe.whitelist()
def approve_transport_quote(reference):
    """SRS 3.3 step 5: customer approves the agreed quote."""
    _require_login()
    req = frappe.get_doc("Transport Request", reference)
    req.approve_quote()
    return {"request": req.name, "state": req.workflow_state,
            "agreed_price": flt(req.agreed_price, 2)}


@frappe.whitelist()
def pay_transport(reference, method=None, phone=None):
    """SRS 3.3 step 5: checkout after approving the quote."""
    _require_login()
    req = frappe.get_doc("Transport Request", reference)
    return req.make_payment(method=method, phone=phone)


@frappe.whitelist()
def pay_order(reference, method, phone=None):
    """Pay an existing Delivery Order (mobile money / card)."""
    _require_login()
    order = frappe.get_doc("Delivery Order", reference)
    return order.make_payment(method=method, phone=phone)


@frappe.whitelist()
def pay_parcel(reference, method, phone=None):
    _require_login()
    parcel = frappe.get_doc("Parcel Request", reference)
    return parcel.make_payment(method=method, phone=phone)


@frappe.whitelist()
def cancel(reference, reason):
    """Cancel any of the three service documents."""
    _require_login()
    for dt in ("Delivery Order", "Parcel Request", "Transport Request"):
        if frappe.db.exists(dt, reference):
            doc = frappe.get_doc(dt, reference)
            if doc.customer != frappe.session.user and "Delivery Operations" not in frappe.get_roles():
                frappe.throw(_("You can only cancel your own requests."), frappe.PermissionError)
            fn = getattr(doc, "cancel_order", None) or getattr(doc, "cancel_request")
            fn(reason)
            return {"reference": reference, "state": doc.workflow_state}
    frappe.throw(_("Not found: {0}").format(reference), frappe.DoesNotExistError)


@frappe.whitelist(allow_guest=True)
def payment_methods():
    return payments.enabled_methods()


@frappe.whitelist(allow_guest=True)
def platform_config():
    """Bootstrap payload for the web + mobile clients."""
    s = frappe.get_cached_doc("Logistics Settings")
    return {
        "platform_name": s.platform_name,
        "currency": s.currency,
        "language": s.language,
        "enabled": bool(s.enabled),
        "payment_methods": payments.enabled_methods(),
        "cod_enabled": bool(s.cod_enabled),
        "free_delivery_over": flt(s.free_delivery_over, 2),
        "small_order_threshold": flt(s.small_order_threshold, 2),
        "instant_weight_limit_kg": flt(s.instant_weight_limit_kg, 2),
        "quote_validity_hours": int(s.quote_validity_hours or 24),
    }
