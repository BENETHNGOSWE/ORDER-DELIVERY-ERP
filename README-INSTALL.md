# Delivery & Logistics — ERPNext app installer

Multi-service delivery platform for ERPNext 16 / Frappe 16:
**Food Delivery, Retail Shopping, Point-to-Point Parcel Delivery,
Negotiated Transport Routing** — with Customer, Merchant, Operations and
Driver web portals.

---

## What is in this zip

```
delivery-app/
├── install.sh          one-shot installer (run this)
├── README-INSTALL.md   this file
└── delivery/           the Frappe app
    ├── pyproject.toml
    └── delivery/
        ├── hooks.py, install.py, permissions.py, portal.py, tasks.py
        ├── modules.txt, demo_data.py, locale/sw.csv
        ├── delivery_logistics/     14 DocTypes + state machine, billing, payments
        ├── api/                    customer / merchant / operations / driver
        ├── www/delivery/           10 portal pages
        ├── public/                 portal JS + CSS (no build step needed)
        └── tests/                  50 unit + integration tests
```

---

## Install — three commands

From your laptop, copy the zip into the container and run the installer.

```bash
# 1. from the host (your laptop), copy the zip in
docker cp ~/Downloads/delivery-app.zip \
  backend-ckbvuki7zcatvrqfgfl3i3bw:/home/frappe/

# 2. get a shell in the container
docker exec -it backend-ckbvuki7zcatvrqfgfl3i3bw bash

# 3. unpack and install
cd ~
unzip delivery-app.zip || python3 -m zipfile -e delivery-app.zip .
cd delivery-app
./install.sh erpnext.kodatechnologies.co.tz
```

Then **restart the container** (`bench restart` does not work in
frappe_docker):

```bash
docker restart backend-ckbvuki7zcatvrqfgfl3i3bw
```

Open `https://erpnext.kodatechnologies.co.tz/delivery`.

Add `--demo` to the install command to also seed demo merchants, a 24-item
catalogue, three drivers and demo logins (password `Sw!ftLog1stics26`).
**Do not use `--demo` on a live site** — it creates users with a published
password.

---

## What the installer does

1. Copies the app to `~/frappe-bench/apps/delivery`
2. Adds `delivery` to `sites/apps.txt`
3. Byte-compiles the app as a sanity check
4. `bench --site <site> install-app delivery` — creates the 14 DocTypes and runs
   `after_install`, which creates four roles (`Delivery Customer`,
   `Merchant User`, `Delivery Operations`, `Driver`), the Logistics Settings
   singleton (currency **TZS**), 7 Dar es Salaam delivery zones and 4 parcel
   weight bands
5. Copies `public/` to `sites/assets/delivery/`
6. Clears the cache

On a re-run it detects the app is already installed and runs `migrate` instead.

## What it deliberately does **not** do

| Not done | Why |
|---|---|
| `bench build` | Forbidden in production containers — it corrupts the shared assets volume. The portal ships plain JS/CSS, so copying is equivalent. |
| `bench get-app` | Not available in production images. The app is copied in directly. |
| `bench restart` | Does not work in containers. Restart via the orchestrator. |
| Set `base_template` | That hook restyles the **whole site including the desk**. The portal pages are standalone instead. |
| Add `website_redirects` | Would hijack your site's homepage. |
| Use `web_include_js/css` | Would inject portal assets into **every** page on your site. Each portal page loads its own. |
| Redirect `/` | Your existing homepage is untouched. |

All portal routes are namespaced under `/delivery/`, so nothing collides with
routes your site already serves (`/`, `/home`, `/track`, `/cart`, `/me`, …).

---

## Portal routes

| Route | Actor |
|---|---|
| `/delivery` | landing + open merchants |
| `/delivery/menu` | food & retail catalogue |
| `/delivery/cart` | cart + checkout |
| `/delivery/parcel` | parcel request with instant quote |
| `/delivery/transport` | multi-stop itinerary |
| `/delivery/track?ref=…` | public tracking |
| `/delivery/me` | customer dashboard |
| `/delivery/merchant` | merchant portal |
| `/delivery/operations` | operations console |
| `/delivery/driver` | driver dashboard |

Roles are mapped to their portal automatically on login. Users who hold none of
the four delivery roles are completely unaffected — the hook returns an empty
string and Frappe uses its normal default.

---

## Order lifecycle

```
REQUESTED → UNDER_REVIEW → PRICE_AGREED → PENDING → ACCEPTED
          → PREPARING → DRIVER_ASSIGNED → PICKED_UP → COMPLETED   (+ CANCELLED)
```

| Service | Path |
|---|---|
| Food / Retail | `PENDING` → `ACCEPTED` → `PREPARING` → … (priced at checkout) |
| Parcel | `REQUESTED` → instant `PRICE_AGREED`, **or** `UNDER_REVIEW` when heavy / oversized / uncategorised → `PRICE_AGREED` |
| Transport | `UNDER_REVIEW` → `PRICE_AGREED` (fare typed by staff after the call) → `ACCEPTED` → … |

Payment is **blocked** on a transport request until a fare has been agreed.

---

## Payments

Cash On Delivery, M-Pesa, Tigo Pesa and Card, all enabled in
**Logistics Settings**.

`simulate_payment_gateways` is **ON** by default, so mobile-money calls are
served by an in-process simulator — useful for testing, and every reference it
issues is prefixed `SIM` so it cannot be mistaken for a real settlement.

**Before taking real money:** turn `simulate_payment_gateways` off and register
an adapter in `delivery/delivery_logistics/payments.py` → `ADAPTERS`. With
simulation off and no adapter registered, the code **refuses** to record a
payment rather than pretending one happened.

COD is a real payment leg: it creates a Payment Transaction that the driver
settles at handoff, which is what makes driver remittance auditable.

---

## Mobile app

Every portal call is a plain whitelisted endpoint, so a Flutter / React Native
app uses the same surface:

```
POST /api/method/delivery.api.customer.<fn>
POST /api/method/delivery.api.merchant.<fn>
POST /api/method/delivery.api.operations.<fn>
POST /api/method/delivery.api.driver.<fn>

Authorization: token <api_key>:<api_secret>
```

`delivery.api.customer.platform_config` is the bootstrap call (platform name,
currency, enabled payment methods, thresholds). 54 whitelisted endpoints in
total.

---

## Verification status — read this

The app was developed and run end-to-end against a live Frappe 16.31 /
ERPNext 16.32 instance: 50 unit + integration tests passed and 48 HTTP
end-to-end checks passed against the running server.

**That sandbox has since been reset and its database destroyed, so those suites
could not be re-run before this zip was produced.** What was verified
statically on the shipped code instead (`verify_static.py`, 36 checks):

- all 50 Python modules compile
- all 14 DocType definitions are valid, correctly moduled, child tables flagged,
  every `Table` field links a real child DocType
- **218 field references resolve** against the DocType schemas — this is the
  check that catches `Unknown column 'x'` at request time; it was proven to
  fail on two deliberately injected defects before being trusted
- all 38 endpoints referenced by the pages exist and are whitelisted (54 total)
- every Jinja include and `/assets/...` path resolves
- no `base_template`, no `website_redirects`, no global asset injection

**Not re-verified:** the runtime test suites, and the live HTTP flows. Expect to
exercise the four workflows once on staging before going live. The install
script byte-compiles the app before touching your site, and `install-app`
validates every DocType as it creates it, so a structural problem will surface
immediately rather than later.

---

## Rollback

```bash
cd ~/frappe-bench
bench --site erpnext.kodatechnologies.co.tz uninstall-app delivery
rm -rf apps/delivery sites/assets/delivery
sed -i '/^delivery$/d' sites/apps.txt
bench --site erpnext.kodatechnologies.co.tz clear-cache
```

Then restart the container.

---

## Making it survive a container rebuild

`docker cp` puts the app in the container's writable layer, so it survives
restarts but **not** `docker compose up --force-recreate` or an image-tag
change. For a durable install, bake the app into a custom image:

```dockerfile
# Dockerfile
FROM frappe/erpnext:v16.32.3
COPY --chown=frappe:frappe delivery /home/frappe/frappe-bench/apps/delivery
RUN echo "delivery" >> /home/frappe/frappe-bench/sites/apps.txt
```

Build and push it, point your compose file at that tag, recreate, then run
`bench --site all migrate`.
