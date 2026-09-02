# Multi-Service Delivery & Logistics Platform

**ERPNext 16 app** implementing the SRS v2.2.0 web platform scope: **Food Delivery,
Retail Shopping, Point-to-Point Parcel Delivery** and **Negotiated Transport Routing**.

Built and verified on Frappe v16.31.0 / ERPNext v16.32.3 (Python 3.14, Node 24,
MariaDB 11.8, Redis 8).

---

## 1. What runs here

| Component | Version / value |
|---|---|
| Frappe | 16.31.0 (`version-16`) |
| ERPNext | 16.32.3 (`version-16`) |
| Delivery app | 1.0.0 |
| Site | `logistics.test` |
| Python | 3.14.7 (Frappe v16 requires `>=3.14,<3.15`) |
| Node | 24 (Frappe v16 requires `>=24`) |
| MariaDB | 11.8.6 — `utf8mb4` / `utf8mb4_unicode_ci` |
| Redis | 8.0.2 — cache/socketio `13000`, queue `11000` |
| Currency | TZS (switchable to USD in settings) |

**Server:** gunicorn on `0.0.0.0:8000`.

---

## 2. Logins

All demo accounts share the password `Sw!ftLog1stics26`.

| Role | Login | Portal |
|---|---|---|
| Administrator (desk) | `Administrator` / `admin` | `/app` |
| Customer | `customer@demo.test` | `/me` |
| Merchant — Swahili Grill | `merchant@demo.test` | `/merchant` |
| Merchant — Kariakoo Mart | `merchant2@demo.test` | `/merchant` |
| Merchant — Masaki Cafe | `merchant3@demo.test` | `/merchant` |
| Operations / Admin | `ops@demo.test` | `/operations` |
| Driver — DRV-001 (motorcycle, 20 kg, food+parcel) | `driver@demo.test` | `/driver` |
| Driver — DRV-002 (van, 800 kg, all three) | `driver2@demo.test` | `/driver` |
| Driver — DRV-003 (car, 300 kg, parcel+transport) | `driver3@demo.test` | `/driver` |

Demo catalogue: 3 merchants, 24 items, 7 Dar es Salaam zones, 4 parcel weight
categories.

---

## 3. Web pages

| Route | Actor | Purpose |
|---|---|---|
| `/` → `/home` | Customer | Service landing + vendor browser |
| `/menu` | Customer | Merchant catalogue |
| `/cart` | Customer | Cart & checkout |
| `/parcel` | Customer | Parcel request + instant quote |
| `/transport` | Customer | Multi-stop itinerary + reference fare |
| `/track?ref=…` | Anyone | Live status, agreed pricing, audit trail |
| `/me` | Customer | Dashboard across all four services |
| `/merchant` | Merchant | Inbox, accept/reject, catalogue & stock |
| `/operations` | Operations | Review queue, tariffs, negotiation, dispatch, settings |
| `/driver` | Driver | Jobs, pickup, OTP handoff, earnings |

---

## 4. Master state machine (SRS §5)

`delivery/delivery_logistics/state_machine.py` is the **single source of truth**.
Nothing else may write `workflow_state`.

```
REQUESTED → UNDER_REVIEW → PRICE_AGREED → PENDING → ACCEPTED
          → PREPARING → DRIVER_ASSIGNED → PICKED_UP → COMPLETED   (+ CANCELLED)
```

| Service | Path | Notes |
|---|---|---|
| Food / Retail | REQUESTED → PENDING → ACCEPTED → PREPARING → DRIVER_ASSIGNED → PICKED_UP → COMPLETED | No `UNDER_REVIEW` — priced at checkout |
| Parcel | REQUESTED → (UNDER_REVIEW → PRICE_AGREED) → … | Review only for custom/heavy/oversized |
| Transport | REQUESTED → UNDER_REVIEW → PRICE_AGREED → … | Fare **must** be agreed before payment |

`CANCELLED` is reachable from every non-terminal state. `COMPLETED` and
`CANCELLED` are terminal.

---

## 5. Pricing models

| Service | Model | Rules |
|---|---|---|
| Food / Retail | Instant | items + zone/distance fee + small-order fee + COD fee; free over threshold |
| Parcel | Instant **or** manual | Weight category → instant. Over 25 kg, any dimension over 100 cm, or no matching category → `UNDER_REVIEW`, Operations sets the tariff |
| Transport | Negotiated | System computes a **reference** fare only; `agreed_price` (typed by Operations after the phone call) is binding |

---

## 6. Payments

| Method | Gateway id | Behaviour |
|---|---|---|
| Cash On Delivery | `cod` | Settled by the driver at handoff (records collected amount + change due) |
| M-Pesa | `mpesa` | STK-push shaped |
| Tigo Pesa | `tigo_pesa` | Push shaped |
| Card | `card` | Stripe shaped |

`Logistics Settings.simulate_payment_gateways` is **ON**, so every gateway call
goes to an in-process simulator and the whole flow is testable with no
credentials. Turn it off and register a real client in
`delivery/delivery_logistics/payments.py → ADAPTERS` to go live. Until then a
live adapter refuses to run rather than faking a charge.

Every payment — including COD — creates a **Payment Transaction** record, which
is the remittance ledger for drivers.

---

## 7. REST API (mobile-ready)

All endpoints are whitelisted and work with a Frappe session **or** an API
key/secret, so a Flutter / React Native app consumes them unchanged.

```
POST /api/method/delivery.api.customer.<fn>
POST /api/method/delivery.api.merchant.<fn>
POST /api/method/delivery.api.operations.<fn>
POST /api/method/delivery.api.driver.<fn>
```

### Bootstrap
| Endpoint | Auth | Returns |
|---|---|---|
| `customer.platform_config` | guest | platform name, currency, enabled payment methods, thresholds |
| `customer.list_merchants` | guest | open vendors, filterable by `service_type` / `search` |
| `customer.merchant_catalog` | guest | published items, grouped by category |
| `customer.zones` | guest | delivery zones and fees |
| `customer.parcel_weight_categories` | guest | tariff bands |
| `customer.payment_methods` | guest | enabled methods |

### Quotes
| Endpoint | Notes |
|---|---|
| `customer.quote_delivery_fee` | `zone`, `distance_km`, `items_total` |
| `customer.quote_parcel` | returns `needs_review`, `is_heavy`, `is_oversized`, `tariff_amount` |
| `customer.quote_transport` | reference fare only, never binding |

### Transactions
| Endpoint | Notes |
|---|---|
| `customer.place_order` | food/retail → `PENDING` |
| `customer.place_parcel_request` | auto-routes heavy/oversized to `UNDER_REVIEW` |
| `customer.place_transport_request` | returns `TR-YYYY-NNNN`, starts `UNDER_REVIEW` |
| `customer.approve_transport_quote` | customer accepts the agreed fare |
| `customer.pay_order` / `pay_parcel` / `pay_transport` | mobile money / card |
| `customer.track` | public tracking by reference |
| `customer.my_orders` / `my_parcels` / `my_transport` | dashboards |
| `customer.cancel` | with reason |

### Merchant
`merchant.whoami`, `profile`, `set_open`, `catalog`, `add_item`, `update_item`,
`set_stock`, `orders`, `order_detail`, `pending_orders`, `accept_order`,
`reject_order`, `stats`

### Operations
`operations.review_queue`, `transport_detail`, `set_parcel_tariff`,
`reject_parcel`, `log_agreed_price`, `record_contact`, `available_drivers`,
`assign_driver`, `suggest_driver`, `dashboard`, `update_settings`, `all_documents`

### Driver
`driver.profile`, `set_availability`, `my_jobs`, `job_detail`, `confirm_pickup`,
`complete_handoff` (OTP), `advance_transport_stop`, `my_earnings`

### Mobile auth
Use Frappe token auth — no session/cookie handling needed:

```
Authorization: token <api_key>:<api_secret>
```

Generate per driver/customer under **User → API Access**.

---

## 8. Security model

Row-level checks in `delivery/permissions.py`, enforced on every API call:

* **Customer** — only their own documents
* **Merchant** — only orders against their own merchant record
* **Driver** — only jobs assigned to their driver record
* **Operations / System Manager** — everything

Verified by tests: a customer cannot open the operations console, a merchant
cannot read another merchant's catalogue, a guest cannot place an order, a wrong
handoff OTP is rejected, and payment is blocked before a transport fare is agreed.

---

## 9. Verification

```bash
# unit + integration (50 tests)
bench --site logistics.test run-tests --app delivery

# HTTP end-to-end against the live server (48 checks)
python3 /home/user/verify_http_e2e.py
```

Both suites are green. The HTTP suite drives the deployed server as each actor
and asserts the complete SRS workflow for all four services.

---

## 10. Running it

```bash
# services
redis-server --port 13000 --daemonize yes
redis-server --port 11000 --daemonize yes
mariadbd-safe --user=mysql --datadir=/var/lib/mysql &

# app server
cd ~/frappe-bench
env/bin/gunicorn --chdir sites --bind 0.0.0.0:8000 \
  --workers 2 --worker-class gthread --threads 4 frappe.app:application

# demo data
bench --site logistics.test console   # then: from delivery.demo_data import seed; seed()
bench --site logistics.test console   # reset with: from delivery.demo_data import reset; reset()
```

---

## 11. Known sandbox limits

* **Desk UI needs the full asset build.** `bench build` is OOM-killed at 1.9 GB
  RAM, so the JS bundles are stubs and `sites/assets/assets.json` was
  hand-written to point at the CSS bundles the interrupted build did produce.
  The **portal** is unaffected — it uses its own self-contained JS/CSS — but the
  `/app` desk will not be interactive here. On a 4 GB+ host, run `bench build`
  and the desk works normally.
* **Email, background jobs and the scheduler are off**, matching the web-only
  SRS scope.
* Swap (4 GB) was added so migrations could complete.

---

## 12. DocTypes

`Delivery Order`, `Delivery Order Item`, `Parcel Request`, `Transport Request`,
`Transport Stop`, `Merchant`, `DL Menu Item`, `Delivery Zone`,
`Parcel Weight Category`, `Delivery Driver`, `Dispatch Trip`,
`Dispatch Trip Stop`, `Payment Transaction`, `Logistics Settings`.

Names were chosen to avoid colliding with ERPNext's own `Delivery Trip`,
`Delivery Stop` and `Delivery Settings`.

---

## Installing onto an existing site

Two things to check before installing on a site that already has content.

### Route collisions in the database

Portal routes live under `/delivery/`. Frappe resolves **Web Page documents
before `www/` files**, so a `Web Page` record with `route = delivery` will
shadow this app's landing page and return a 500 if its own template is missing.

Check with:

```bash
bench --site <site> execute delivery.maintenance.audit_pages
```

That lists every Web Page whose `{% include %}`/`{% extends %}` target cannot be
resolved, and flags any that collide with a portal route. To switch the broken
ones off (reversible — set `published` back to 1):

```bash
bench --site <site> execute delivery.maintenance.unpublish_broken_pages
bench --site <site> clear-website-cache
```

### CSRF token

The portal pages are standalone and do not extend Frappe's base template, so
they have no server-rendered CSRF token. The token is fetched once by
`delivery_portal.js` from `delivery.portal.session_csrf` over GET (which Frappe
does not CSRF-protect) and then sent on every POST.

It is deliberately **not** rendered from Jinja: a wrong accessor in a template
expression raises during render and takes the whole page down with a 500.

`bench --site <site> execute delivery.maintenance.probe_csrf` reports which
accessor works on your Frappe version.

## Diagnostics

| Command | Purpose |
|---|---|
| `delivery.maintenance.audit_pages` | Web Pages with unresolvable template includes |
| `delivery.maintenance.unpublish_broken_pages` | switch them off (reversible) |
| `delivery.maintenance.recent_errors` | tail of the Error Log |
| `delivery.maintenance.home_page` | what the site serves at `/` |
| `delivery.maintenance.probe_csrf` | which CSRF accessor works here |
| `delivery.maintenance.probe_templates` | render every portal page, report failures |
