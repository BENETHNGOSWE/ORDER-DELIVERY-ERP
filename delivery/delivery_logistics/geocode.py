"""
Lightweight address geocoding for the live tracking map.

The tracking map needs latitude/longitude for the pickup and drop-off points.
Orders store addresses as free text (e.g. "Mbezi Street, Kariakoo"), so we turn
that text into coordinates with the free OpenStreetMap **Nominatim** service
(the same data shown on the Leaflet map). Results are cached and, where the
DocType has coordinate fields, written back so we only geocode an address once.

Exact coordinates always win: if a Delivery Order already has
``delivery_latitude/longitude`` (or a Merchant has ``latitude/longitude``) those
are used and no network call is made.
"""
import json

import frappe
from frappe.utils import flt

NOMINATIM = "https://nominatim.openstreetmap.org/search"
DEFAULT_CITY = "Dar es Salaam, Tanzania"
_CACHE_HKEY = "delivery_geocode"


def _cache_get(key):
	try:
		val = frappe.cache().hget(_CACHE_HKEY, key)
		return json.loads(val) if val else None
	except Exception:
		return None


def _cache_set(key, value):
	try:
		frappe.cache().hset(_CACHE_HKEY, key, json.dumps(value))
	except Exception:
		pass


def _nominatim_lookup(query):
	import requests  # provided by Frappe
	resp = requests.get(
		NOMINATIM,
		params={"format": "jsonv2", "q": query, "limit": 1},
		headers={"User-Agent": "delivery-logistics-app/1.1 (ERPNext)"},
		timeout=4,
	)
	if resp.status_code == 200 and resp.json():
		hit = resp.json()[0]
		return flt(hit.get("lat"), 6), flt(hit.get("lon"), 6)
	return None, None


def geocode(address, area=None, city=None):
	"""
	Return ``(latitude, longitude)`` for an address string, or ``(None, None)``.

	Uses OpenStreetMap Nominatim. Exact streets are often unmapped, so we try
	progressively coarser queries (full address -> area -> city) and return the
	first match. Network failures degrade gracefully to ``(None, None)``.
	"""
	address = (address or "").strip()
	city = (city or DEFAULT_CITY).strip()
	area = (area or "").strip()

	# build a fallback ladder: most specific -> area -> city
	queries = []
	if address:
		base = address
		queries.append(base)
		if city.lower() not in base.lower():
			queries.append("{0}, {1}".format(base, city))
	if area:
		queries.append(area)
		if city.lower() not in area.lower():
			queries.append("{0}, {1}".format(area, city))
	queries.append(city)  # last resort so a pin still appears in the right metro

	# de-duplicate, preserve order
	seen, ladder = set(), []
	for q in queries:
		q = q.strip()
		if q and q not in seen:
			seen.add(q)
			ladder.append(q)

	for query in ladder:
		cached = _cache_get(query)
		if cached:
			return cached[0], cached[1]
		try:
			lat, lng = _nominatim_lookup(query)
		except Exception:
			# offline / blocked / timeout - try a coarser query
			frappe.log_error(title="Delivery geocode failed", message=query)
			lat = lng = None
		if lat and lng:
			_cache_set(query, [lat, lng])
			return lat, lng

	return None, None


def order_points(doc, dt):
	"""
	Resolve ``(pickup, dropoff)`` dicts using STORED coordinates only.

	Called by the live tracking request, so it is instant and never does network
	I/O. Missing coordinates are filled in the background by
	:func:`backfill_coordinates` (queued at checkout, or run once for history).
	"""
	pickup = dropoff = None

	if dt == "Delivery Order":
		dlat = flt(doc.get("delivery_latitude"))
		dlng = flt(doc.get("delivery_longitude"))
		if dlat and dlng:
			dropoff = {"lat": dlat, "lng": dlng,
			           "label": doc.get("delivery_address") or "Delivery address"}
		merchant = doc.get("merchant")
		if merchant:
			mlat = flt(frappe.db.get_value("Merchant", merchant, "latitude"))
			mlng = flt(frappe.db.get_value("Merchant", merchant, "longitude"))
			if mlat and mlng:
				mname = frappe.db.get_value("Merchant", merchant, "merchant_name")
				pickup = {"lat": mlat, "lng": mlng, "label": mname or "Pickup"}

	elif dt == "Parcel Request":
		dlat = flt(doc.get("dropoff_latitude"))
		dlng = flt(doc.get("dropoff_longitude"))
		if dlat and dlng:
			dropoff = {"lat": dlat, "lng": dlng,
			           "label": doc.get("dropoff_address") or "Drop-off"}
		plat = flt(doc.get("pickup_latitude"))
		plng = flt(doc.get("pickup_longitude"))
		if plat and plng:
			pickup = {"lat": plat, "lng": plng,
			          "label": doc.get("pickup_address") or "Pickup"}

	return pickup, dropoff


def _geocode_merchant(merchant):
	mlat = flt(frappe.db.get_value("Merchant", merchant, "latitude"))
	mlng = flt(frappe.db.get_value("Merchant", merchant, "longitude"))
	if mlat and mlng:
		return
	m = frappe.db.get_value("Merchant", merchant,
	                        ["full_address", "area", "city"], as_dict=True)
	if not m:
		return
	lat, lng = geocode(m.full_address or m.area, area=m.area,
	                   city=m.city or "Dar es Salaam")
	if lat and lng:
		try:
			frappe.db.set_value("Merchant", merchant,
			                    {"latitude": lat, "longitude": lng},
			                    update_modified=False)
		except Exception:
			pass


def backfill_coordinates(reference=None, doctype=None, full=False):
	"""
	Background geocoding (network). Fills stored coordinates for addresses that
	have none. Run queued from checkout, or once with full=True for history.
	"""
	if full:
		for m in frappe.get_all("Merchant",
		                        filters={"latitude": ["in", (None, 0)]},
		                        pluck="name", limit=500):
			try:
				_geocode_merchant(m)
			except Exception:
				frappe.log_error(title="Delivery backfill merchant failed", message=m)
		for name in frappe.get_all("Delivery Order",
		                        filters={"delivery_latitude": ["in", (None, 0)]},
		                        pluck="name", limit=1000):
			try:
				backfill_coordinates(reference=name, doctype="Delivery Order")
			except Exception:
				frappe.log_error(title="Delivery backfill order failed", message=name)
		frappe.db.commit()
		print("Coordinate backfill complete.")
		return {"status": "ok", "scope": "full"}

	if reference:
		dt = doctype or "Delivery Order"
		if not frappe.db.exists(dt, reference):
			return {"status": "missing"}
		doc = frappe.get_doc(dt, reference)
		if dt == "Delivery Order":
			_geocode_merchant(doc.get("merchant"))
			if not (flt(doc.get("delivery_latitude")) and flt(doc.get("delivery_longitude"))):
				lat, lng = geocode(doc.get("delivery_address"),
				                   area=doc.get("delivery_zone"),
				                   city="Dar es Salaam")
				if lat and lng:
					frappe.db.set_value(dt, reference,
					                    {"delivery_latitude": lat,
					                     "delivery_longitude": lng},
					                    update_modified=False)
		frappe.db.commit()
		return {"status": "ok", "reference": reference}
	return {"status": "noop"}


# ---------------------------------------------------------------------------
# Place autocomplete (for the checkout "search your location" box)
# ---------------------------------------------------------------------------
PHOTON = "https://photon.komoot.io/api/"
# Dar es Salaam centre used to bias nearby results
_BIAS_LAT, _BIAS_LNG = -6.7924, 39.2083


def search_places(query, lat=None, lng=None, limit=8):
	"""
	Autocomplete registered places (hotels, apartments, businesses, streets,
	areas) via the free OpenStreetMap-based Photon service. Returns a list of
	``{"label", "lat", "lng", "type"}`` biased around Dar es Salaam.
	"""
	query = (query or "").strip()
	if len(query) < 2:
		return []

	params = {
		"q": query,
		"limit": limit,
		"lang": "en",
		"lat": lat if lat is not None else _BIAS_LAT,
		"lon": lng if lng is not None else _BIAS_LNG,
	}
	try:
		import requests
		resp = requests.get(PHOTON, params=params,
		                    headers={"User-Agent": "delivery-logistics-app/1.1 (ERPNext)"},
		                    timeout=8)
		features = resp.json().get("features", []) if resp.status_code == 200 else []
	except Exception:
		frappe.log_error(title="Delivery place search failed", message=query)
		return []

	results = []
	for f in features:
		geom = f.get("geometry", {}).get("coordinates", [])
		props = f.get("properties", {})
		if len(geom) < 2:
			continue
		glng, glat = geom[0], geom[1]

		name = props.get("name") or ""
		street = props.get("street") or ""
		house = props.get("housenumber") or ""
		district = props.get("district") or props.get("locality") or props.get("county") or ""
		city = props.get("city") or props.get("state") or ""

		# build a human label
		head = name or " ".join(x for x in (street, house) if x)
		tail = ", ".join(x for x in (district, city) if x and x != head)
		label = head if not tail else "{0}, {1}".format(head, tail)
		if not label:
			continue

		results.append({
			"label": label,
			"lat": flt(glat, 6),
			"lng": flt(glng, 6),
			"type": props.get("osm_value") or props.get("type") or "",
		})
	return results
