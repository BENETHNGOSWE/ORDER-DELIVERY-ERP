# Delivery & Logistics — System Setup & Content Guide

Everything is running at:

- **Customer app:** https://delivery.kodatechnologies.co.tz/delivery
- **Parcel page:** https://delivery.kodatechnologies.co.tz/delivery/parcel
- **Transport page:** https://delivery.kodatechnologies.co.tz/delivery/transport
- **Admin Desk:** https://delivery.kodatechnologies.co.tz/app  (log in as **Administrator**)

This guide fills the system with content so merchants, items, prices, the home
slider/banners, drivers and orders all work. Run the docker commands from the
server as `root`; do the rest in Desk in the browser.

---

## 0. Why the home page says "Loading…" and the slider is empty

The portal is up, but it has **no data yet**:

- The hero carousel shows nothing because there are no **Home Banner** records
  (it shows branded default slides once the app is fully installed).
- "Loading merchants / items / offers" stays because no **Merchant** and **DL
  Menu Item** records exist.

Two commands on the server verify the app is installed and load starter data:

```bash
P=l48ssk080w844co8sswo8o4s
B=$(docker ps --format '{{.Names}}' | grep "backend-$P")

# 1) confirm the delivery app is installed (must list frappe, erpnext, delivery)
docker exec "$B" bench --site delivery.kodatechnologies.co.tz list-apps

# 2) load demo merchants, 24 menu items, drivers and demo users (idempotent)
docker exec "$B" bench --site delivery.kodatechnologies.co.tz execute delivery.demo_data.seed

# 3) clear caches
docker exec "$B" bench --site delivery.kodatechnologies.co.tz clear-cache
docker exec "$B" bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

After step 2, hard-refresh `/delivery` — merchants, the item grid, offers and the
default slider appear. The demo password for the created users is
`Sw!ftLog1stics26`.

If you want to start with a **blank** system and enter real data, clear the
demo later with:

```bash
docker exec "$B" bench --site delivery.kodatechnologies.co.tz execute delivery.demo_data.reset
```

---

## 1. First-run system settings (Desk → Setup / Settings)

Open each from the Awesome Bar (Ctrl+G / the search box top-left):

1. **Logistics Settings** (search "Logistics Settings") — the platform config:
   - **Platform Name**: e.g. `Delivery`
   - **Currency**: `TZS`
   - **Enabled**: ✔ (turns the customer portal on)
   - **COD Enabled**: ✔ for Cash on Delivery
   - **Free Delivery Over**: e.g. `15000` (free delivery above this subtotal)
   - **Small Order Threshold**: e.g. `5000`
   - **Instant Weight Limit (kg)**: e.g. `25`
   - **Quote Validity (hours)**: e.g. `24`
   - **Payment Methods**: add the methods you accept (e.g. `Cash On Delivery`,
     `M-Pesa`, `Tigo Pesa`, `Airtel Money`, `Bank Transfer`). These appear in the
     parcel/checkout **Payment** dropdown.
   - Save.
2. **System Settings**: Country = Tanzania, Timezone = `Africa/Dar_es_Salaam`,
   Currency Precision = 0 (whole TZS), Language = English.
3. **File Upload Limit**: System Settings → set **Max File Size** to ~`52428800`
   (50 MB) so banner/product images upload without error.

---

## 2. Delivery zones & fees

The checkout delivery fee is computed from zones. Search **Delivery Zone** → New:

| Field | Example |
|---|---|
| Zone Name | `Masaki` |
| City | `Dar es Salaam` |
| Base Delivery Fee | `3000` |
| Per KM Fee | `500` |
| Typical Distance (km) | `12` |
| Enabled | ✔ |
| Supported Services | `Food, Parcel, Transport` |

Add a few (Masaki, Kariakoo, Mwenge, Kinondoni, etc.).

---

## 3. Home slider / hero banners (the rotating banner)

Search **Home Banner** → **New**. One record = one slide.

| Field | What to enter |
|---|---|
| **Banner Title** | Internal label, e.g. `Ramadan Promo` |
| **Banner Image** | Upload the slide artwork — **recommended 1600×520 px (~3:1)**, JPG/PNG, < 1–2 MB |
| **Enabled** | ✔ |
| **Sort Order** | `1`, `2`, `3`… (lower = first) |
| **Subtitle** *(optional)* | Short overlay text on the image |
| **Button Label** *(optional)* | e.g. `Order Now` |
| **Button Link** *(optional)* | e.g. `/delivery/parcel` |

- Add **at least one** enabled banner; with several, they auto-rotate every 5 s.
- Leave Subtitle/Button blank to show the image full-bleed.
- Dark/left-weighted artwork reads best (a dark gradient is auto-overlaid on the
  left for text).

**The circular promo photos** on the three small banners (Mega Offers / Groceries
/ Send a parcel) ship as static images; they are not data-driven.

---

## 4. Merchants (shops/restaurants)

Search **Merchant** → **New**. Required: **Merchant ID**, **Merchant Name**,
**Service Type**.

| Field | Guidance |
|---|---|
| Merchant ID | Unique code, e.g. `M-SWAHILI-GRILL` |
| Merchant Name | e.g. `Swahili Grill House` |
| Service Type | `Food`, `Retail`, or `Food/Retail` (controls where they appear) |
| **Status** | Must be **Open** for the shop to show on the portal |
| City / Area / Pickup Address | Shown under the name; area appears on the card |
| Phone / Email | Contact details |
| **Average Prep Time (min)** | e.g. `25` → shows "~25 min" |
| **Minimum Order Value** | e.g. `10000` |
| Delivery Radius (km) | e.g. `15` |
| Commission (%) | Platform commission for reporting |
| **Logo** | Square image ~600×600 (shown on the merchant card) |
| Latitude / Longitude | Shop coords for the map/distance (optional) |
| Portal User | Link a User with the **Merchant User** role so they can manage their catalog |

> ⚠️ Items only appear for merchants whose **Status = Open** and which have
> published items.

---

## 5. Menu items (products)

Search **DL Menu Item** → **New**. Required: **Item Code**, **Item Name**,
**Merchant**, **Standard Rate**.

| Field | Guidance |
|---|---|
| Item Code | Unique SKU, e.g. `SG-PILAU` (used for bulk image matching) |
| Item Name | e.g. `Pilau na Kuku` |
| Merchant | Select the shop |
| Item Type | `Food`, `Retail`, or `Grocery` (drives category tiles) |
| Category | Free text, e.g. `Grill`, `Drinks`, `Groceries` |
| Description | Short line shown on cards |
| Standard Rate | Normal price in TZS, e.g. `12000` |
| Discount Rate | Discount % (shows strikethrough price + "-x%"), e.g. `10` |
| **Item Image** | Upload a square photo ~**600×600 px** |
| Featured | ✔ to pin it / show "Popular" |
| Published On Portal | **must be ✔** to show on the site |
| Available Stock | e.g. `100` |
| Track Stock | ✔ if stock should decrement |
| Prep Time (min) | override if different from the merchant |

**Bulk images:** put product photos in a folder on the server, named by item code
(`SG-PILAU.jpg`, `KM-RICE-5KG.png`…), then:

```bash
docker exec "$B" bench --site delivery.kodatechnologies.co.tz \
  execute delivery.maintenance.bulk_attach_images \
  --kwargs '{"folder":"/home/frappe/product-images"}'
```
(Upload files into that path inside the backend container first; .jpg/.jpeg/.png/
.webp supported.)

---

## 6. Drivers

Search **Delivery Driver** → **New** (name, phone, vehicle, assigned user).
Link a User who has the **Driver** role. The driver uses the driver portal
(`/delivery/driver`) to accept trips; their GPS pings drive the live map.

The `seed` creates demo driver **Baraka Mwangala** (`driver@demo.test`, DRV-001).

---

## 7. Parcel weight bands (parcel pricing)

Search **Parcel Weight Category** → New (or edit the seeded rows):

| Field | Example |
|---|---|
| Category Name | `Small Parcel` |
| Min Weight (kg) / Max Weight (kg) | `0.5` / `2` |
| Base Charge | `3500` |
| Charge Per Extra KG | `250` |
| Enabled | ✔ |

These power the "Get quote" on the Parcel page and the weight-bands table.

---

## 8. Test the customer flows end to end

1. **Order food/retail** — on `/delivery`, pick a category, add items, open the
   cart (Checkout), set the delivery pin on the map, phone + payment, **Place
   order**. The track popup opens automatically.
2. **Track** — `/delivery/track` or the Track link, enter the order reference.
3. **Simulate driver movement** (to see live tracking on a demo order):
   ```bash
   docker exec "$B" bench --site delivery.kodatechnologies.co.tz \
     execute delivery.demo_data.simulate_move \
     --kwargs '{"reference":"DL-ORD-2026-0002"}'
   ```
   Refresh the track page to watch the driver marker move toward the dropoff.
4. **Parcel** — `/delivery/parcel`, get a quote, send the parcel → creates a
   Parcel Request you manage in Desk.
5. **Transport** — `/delivery/transport`, add stops, Estimate, Submit → creates a
   Transport Request; operations approves/agrees the fare.
6. In **Desk**, review **Delivery Order**, **Parcel Request**, **Transport
   Request** under the Delivery Logistics module; move statuses (Accepted →
   Preparing → Driver Assigned → Picked Up → Completed) — the customer tracker
   updates automatically.

---

## 9. Roles / who can do what

In Desk → User, assign:
- **Delivery Operations** — dispatch, pricing, approvals, operations portal
  (`/delivery/operations`).
- **Merchant User** — manages their own shop's menu/orders (`/delivery/merchant`).
- **Driver** — the driver portal (`/delivery/driver`).
- **Delivery Customer** / portal users — My Orders (`/delivery/me`).
- **System Manager** — full setup (you / Administrator).

---

## 10. Updating the app after code changes

The app was installed into the running containers. After a future code push,
**redeploy in Coolify**, then in the backend container:

```bash
docker exec "$B" bench --site delivery.kodatechnologies.co.tz migrate
docker exec "$B" bench --site delivery.kodatechnologies.co.tz clear-cache
docker exec "$B" bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

> Permanent option (recommended for production): bake the delivery app into a
> custom Docker image so you don't re-install after each redeploy. Ask and we'll
> switch the compose to a built image now that the foundation is proven.

---

## 11. Backups

Back up the **mariadb-data** and **sites** volumes in Coolify (Backups tab).
Logical backup anytime:

```bash
docker exec "$B" bench --site delivery.kodatechnologies.co.tz backup --with-files
```
Store the generated files (in `sites/.../private/backups`) off-server.

---

## Quick reference (docker)

```bash
P=l48ssk080w844co8sswo8o4s
B=$(docker ps --format '{{.Names}}' | grep "backend-$P")

# list containers / status
docker ps --format '{{.Names}}\t{{.Status}}'

# logs
docker logs --tail 50 $(docker ps --format '{{.Names}}' | grep "frontend-$P")
docker logs --tail 50 "$B"

# set admin password
docker exec "$B" bench --site delivery.kodatechnologies.co.tz set-admin-password 'NewStrongPass'

# if a redis "server error" ever appears:
docker exec "$B" bench set-config -g redis_cache  "redis://redis-cache:6379"
docker exec "$B" bench set-config -g redis_queue  "redis://redis-queue:6379"
docker exec "$B" bench set-config -g redis_socketio "redis://redis-queue:6379"
```
