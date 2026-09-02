# Delivery & Logistics v1.1.0 — Live Driver Tracking (Leaflet map)

Adds a **live map on `/delivery/track`**: after a driver is assigned/accepts an
order, the customer enters the order reference and watches the driver move on an
**OpenStreetMap / Leaflet** map — same Leaflet engine used in your Sales Team
Tracker.

## What was added

1. **New DocType `Driver Location Log`** — breadcrumb trail of GPS pings
   (driver, order reference, activity, lat/lng, accuracy, timestamp).
   Auto-created when the app migrates.
2. **Driver endpoint** `delivery.api.driver.report_location` — the driver's
   phone posts GPS; it writes a log row and updates the driver's last position.
3. **Public endpoint** `delivery.api.customer.track_route` — returns the driver's
   latest position + route trail for an order (only after a driver is assigned).
4. **Driver portal** (`/delivery/driver`) — a **“Start sharing”** button that uses
   the browser/device GPS (`navigator.geolocation`) and pings automatically.
5. **Track page** (`/delivery/track`) — Leaflet map with a pulsing driver marker,
   the route polyline, breadcrumb dots, driver name/phone popup, and a 10-second
   auto-refresh. No CSS/JS build step (Leaflet loads from the unpkg CDN).

## Install / update on your v16 bench

```bash
cd ~/frappe-v16

# 1. put the app in apps/ (overwrite), then make sure it's registered
#    (if you already installed it from GitHub, just replace apps/delivery with this copy)
cp -r /path/to/erpnext-delivery-logistics/delivery apps/delivery   # see note below
grep -qx delivery sites/apps.txt || echo delivery >> sites/apps.txt

# 2. migrate — this creates the new Driver Location Log doctype
bench --site delivery.localhost migrate

# 3. publish portal assets (JS/CSS; no build needed)
mkdir -p sites/assets/delivery
cp -r apps/delivery/delivery/public/. sites/assets/delivery/

# 4. refresh
bench --site delivery.localhost clear-cache
bench --site delivery.localhost clear-website-cache
```

> **Layout note:** this zip's app package is the inner `delivery/` folder (the one
> containing `hooks.py`, `api/`, `www/`, …). If `apps/delivery` already exists,
> replace its contents with that inner folder. Then `migrate` creates the doctype.

Then **restart the bench** (Ctrl-C and `bench start`, with `nvm use 24`).

## How to test

1. Log in to **/delivery/driver** as a driver user → press **Start sharing**
   (allow the browser location permission; on a phone it uses real GPS).
2. As a customer, open **/delivery/track**, enter the order reference
   (e.g. `DL-ORD-2026-0001`) once the order is in `DRIVER_ASSIGNED` / `PICKED_UP`.
3. The map appears, centres on the driver, and refreshes every 10 seconds, drawing
   the route as new pings arrive.

> Map/geolocation needs a **secure context**. On the laptop use `localhost`;
> for phone testing over LAN (e.g. `https://91.107.220.134`) serve via **HTTPS**
> (or the browser will block GPS). The map itself still loads; only the driver's
> GPS capture requires the permission/HTTPS.

## Permissions
- `Driver Location Log`: System Manager + Delivery Operations full access;
  `Driver` role can create/read their own rows.
- Customers never query the log directly — they only see their order's driver
  position through `track_route`, which requires a valid order reference and an
  assigned driver.
