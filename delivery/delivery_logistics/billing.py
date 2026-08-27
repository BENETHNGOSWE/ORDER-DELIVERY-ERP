"""
Fee engine for all four services - SRS v2.2.0 sections 3.1-3.3 and 4.

Three pricing models:

* **Food / Retail** - instant. Items + zone/distance delivery fee + small-order
  fee + COD handling fee. Free delivery above the configured threshold.
* **Parcel** - instant *or* manual. A matching weight category bills instantly;
  anything heavy, oversized or uncategorised is routed to ``UNDER_REVIEW`` where
  Operations types the tariff. A manually agreed tariff is never overwritten.
* **Transport** - negotiated. The engine only ever produces a *reference* fare.
  The binding number is ``agreed_price``, typed by Operations after the phone
  call (SRS 3.3 step 4).

.. warning::
   ``frappe.utils.flt(value, precision)`` takes a **precision**, not a default.
   ``flt(x, 2500)`` rounds to 2500 decimal places. Always write
   ``flt(x) or default``.
"""
import frappe
from frappe import _
from frappe.utils import flt

SETTINGS_DOCTYPE = "Logistics Settings"

#: Dimension above which a parcel cannot be billed instantly (cm).
DEFAULT_MAX_INSTANT_DIMENSION_CM = 100.0
#: Weight above which a parcel cannot be billed instantly (kg).
DEFAULT_INSTANT_WEIGHT_LIMIT_KG = 25.0


def r2(value):
    """Money is stored to 2 dp."""
    return round(flt(value), 2)


def settings():
    return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def _currency():
    """Platform currency. Falls back to the site default, never to a hardcode."""
    cur = None
    try:
        cur = settings().currency
    except Exception:
        cur = None
    return cur or frappe.db.get_default("currency") or "TZS"


def apply_currency(doc):
    """
    Force the platform currency onto a service document.

    Frappe resolves a ``Currency`` **link** field's default from the global
    default currency (INR on a stock ERPNext site), which silently overrides
    the default declared on the DocType field. Assigning it here is the only
    reliable way to honour the platform setting.
    """
    doc.currency = _currency()
    return doc.currency


def _cfg(field, default=0):
    try:
        value = settings().get(field)
    except Exception:
        value = None
    return flt(value) if flt(value) else flt(default)


# ---------------------------------------------------------------------------
# food / retail (SRS 3.1)
# ---------------------------------------------------------------------------
def zone_fees(zone=None):
    """Base fee + per-km rate for a zone, falling back to platform defaults."""
    base = per_km = distance = 0.0
    if zone and frappe.db.exists("Delivery Zone", zone):
        z = frappe.get_cached_doc("Delivery Zone", zone)
        base = flt(z.base_fee)
        per_km = flt(z.per_km_fee)
        distance = flt(z.distance_km)
    return (base or _cfg("base_delivery_fee", 2000),
            per_km or _cfg("per_km_fee", 500),
            distance)


def estimate_delivery_fee(zone=None, distance_km=0, items_total=0):
    """
    Live delivery-fee preview for the cart (SRS 3.1 step 2).

    Returns a dict so the client can show the working, not just a number.
    """
    base, per_km, zone_distance = zone_fees(zone)
    km = flt(distance_km) or zone_distance
    items_total = flt(items_total)

    fee = base + (per_km * km)

    minimum = _cfg("min_delivery_fee", 1500)
    if fee and fee < minimum:
        fee = minimum

    free_over = _cfg("free_delivery_over")
    is_free = bool(free_over) and items_total >= free_over
    if is_free:
        fee = 0.0

    return {
        "delivery_fee": r2(fee),
        "base_fee": r2(base),
        "per_km_fee": r2(per_km),
        "distance_km": r2(km),
        "free_delivery": is_free,
        "free_delivery_over": r2(free_over),
        "currency": _currency(),
    }


def _item_rate(item):
    """Menu item rate after any discount."""
    rate = flt(item.standard_rate)
    discount = flt(item.discount_rate)
    if discount:
        rate = rate - (rate * discount / 100.0)
    return r2(rate)


def food_retail_totals(order, adjust_stock=False):
    """
    Compute and store every charge on a Delivery Order.

    Items are priced from the live DL Menu Item so the client cannot inflate or
    deflate a rate by tampering with the payload.

    ``adjust_stock`` must only be true on the first save - ``validate`` runs on
    every save, and drawing stock down each time would silently empty the
    merchant's inventory.
    """
    items_total = 0.0
    prep_minutes = []

    for line in order.get("order_items") or []:
        item = frappe.get_cached_doc("DL Menu Item", line.item) \
            if line.item else None
        if not item:
            frappe.throw(_("Unknown menu item: {0}").format(line.item),
                         title=_("Invalid Item"))

        line.item_name = item.item_name
        line.rate = _item_rate(item)
        line.qty = flt(line.qty) or 1
        line.amount = r2(line.rate * line.qty)
        items_total += line.amount

        if adjust_stock and item.track_stock:
            item.available_stock = int(flt(item.available_stock) - line.qty)
            item.save(ignore_permissions=True)
        if item.prep_minutes:
            prep_minutes.append(int(item.prep_minutes))

    order.items_total = r2(items_total)

    fee = estimate_delivery_fee(order.get("delivery_zone"),
                                order.get("delivery_distance_km"),
                                items_total)
    order.delivery_fee = fee["delivery_fee"]

    threshold = _cfg("small_order_threshold")
    small = _cfg("small_order_fee")
    order.small_order_fee = r2(small) if (threshold and items_total < threshold) else 0.0

    order.tax_amount = 0.0

    cod = _cfg("cod_fee")
    order.cod_fee = r2(cod) if (order.get("payment_method") == "Cash On Delivery"
                                and _cfg("cod_enabled", 1)) else 0.0

    order.grand_total = r2(items_total + order.delivery_fee
                           + order.small_order_fee + order.cod_fee
                           + order.tax_amount)

    apply_currency(order)

    if prep_minutes and not order.get("prep_minutes"):
        order.prep_minutes = max(prep_minutes)

    return order


# ---------------------------------------------------------------------------
# parcel (SRS 3.2)
# ---------------------------------------------------------------------------
def weight_category_for(weight_kg):
    """Highest-priority enabled band that contains ``weight_kg``."""
    rows = frappe.get_all(
        "Parcel Weight Category", filters={"enabled": 1},
        fields=["name", "category_name", "min_weight_kg", "max_weight_kg",
                "base_charge", "per_kg_charge", "priority"],
        order_by="priority desc, min_weight_kg asc")

    w = flt(weight_kg)
    for r in rows:
        # max_weight_kg of 0 means "no upper bound"
        upper = flt(r.max_weight_kg)
        if w >= flt(r.min_weight_kg) and (not upper or w <= upper):
            return r
    return None


def parcel_flags(parcel):
    """Heavy / oversized determination against Logistics Settings."""
    limit = _cfg("instant_weight_limit_kg") or DEFAULT_INSTANT_WEIGHT_LIMIT_KG
    max_dim = _cfg("max_instant_dimension_cm") or DEFAULT_MAX_INSTANT_DIMENSION_CM

    weight = flt(parcel.get("weight_kg"))
    dims = [flt(parcel.get(f)) for f in ("length_cm", "width_cm", "height_cm")]

    return {
        "is_heavy": weight > limit,
        "is_oversized": bool(dims) and max(dims) > max_dim,
        "weight_limit_kg": limit,
        "max_dimension_cm": max_dim,
    }


def parcel_billing(parcel):
    """
    Price a parcel.

    Returns ``(needs_review, totals)``. When a manual tariff has already been
    agreed (``billing_type == "Negotiated"``) the stored tariff is preserved -
    the engine never overwrites a price a human agreed.
    """
    flags = parcel_flags(parcel)
    parcel.is_heavy = 1 if flags["is_heavy"] else 0
    parcel.is_oversized = 1 if flags["is_oversized"] else 0

    category = weight_category_for(parcel.get("weight_kg"))
    parcel.weight_category = category.name if category else None

    manual = (parcel.get("billing_type") == "Negotiated"
              and flt(parcel.get("tariff_amount")))

    if manual:
        apply_currency(parcel)
        return False, {"tariff_amount": r2(parcel.tariff_amount), "manual": True}

    if category is None or flags["is_heavy"] or flags["is_oversized"]:
        # SRS 3.2: custom / heavy / oversized -> manual quote
        parcel.billing_type = "Negotiated"
        apply_currency(parcel)
        return True, {
            "tariff_amount": r2(parcel.get("tariff_amount")),
            "needs_review": True,
            "is_heavy": flags["is_heavy"],
            "is_oversized": flags["is_oversized"],
            "reason": _("No standard weight category applies, or the parcel is "
                        "heavy/oversized."),
        }

    weight = flt(parcel.get("weight_kg"))
    base = flt(category.base_charge)
    extra_kg = max(0.0, weight - flt(category.min_weight_kg))
    weight_charge = flt(category.per_kg_charge) * extra_kg
    distance_charge = _cfg("parcel_per_km_fee") * flt(parcel.get("distance_km"))

    subtotal = base + weight_charge + distance_charge

    fragile_pct = _cfg("fragile_surcharge_pct")
    fragile = subtotal * fragile_pct / 100.0 if (parcel.get("is_fragile") and fragile_pct) else 0.0

    parcel.billing_type = "Instant"
    parcel.base_charge = r2(base)
    parcel.weight_charge = r2(weight_charge)
    parcel.distance_charge = r2(distance_charge)
    parcel.fragile_surcharge = r2(fragile)
    parcel.tariff_amount = r2(subtotal + fragile)

    apply_currency(parcel)

    return False, {
        "tariff_amount": parcel.tariff_amount,
        "needs_review": False,
        "is_heavy": False,
        "is_oversized": False,
        "weight_category": category.category_name,
        "base_charge": parcel.base_charge,
        "weight_charge": parcel.weight_charge,
        "distance_charge": parcel.distance_charge,
        "fragile_surcharge": parcel.fragile_surcharge,
        "currency": parcel.currency,
    }


def set_manual_tariff(parcel, amount, note=None):
    """Operations agrees a tariff for a parcel that could not be auto-billed."""
    amount = r2(amount)
    if amount <= 0:
        frappe.throw(_("The agreed tariff must be greater than zero."),
                     title=_("Invalid Tariff"))
    parcel.billing_type = "Negotiated"
    parcel.tariff_amount = amount
    parcel.manual_tariff_note = note
    apply_currency(parcel)
    return amount


# ---------------------------------------------------------------------------
# transport (SRS 3.3) - reference fare only
# ---------------------------------------------------------------------------
def transport_distance(req):
    return r2(sum(flt(s.get("distance_from_prev_km"))
                  for s in (req.get("route_stops") or [])))


def transport_suggested_fare(req):
    """
    Reference fare for a multi-stop itinerary.

    base + (per-km x total km) + (per-stop x intermediate stops).

    This is an *estimate shown to staff*. It is never what the customer is
    charged - ``agreed_price`` is.
    """
    base = _cfg("transport_base_fare", 15000)
    per_km = _cfg("transport_per_km", 1200)
    per_stop = _cfg("transport_per_stop", 3000)

    km = flt(req.get("total_distance_km")) or transport_distance(req)
    stops = len(req.get("route_stops") or [])
    intermediate = max(0, stops - 1)

    return r2(base + (per_km * km) + (per_stop * intermediate))


def quote_validity_hours():
    return int(_cfg("quote_validity_hours") or 24)
