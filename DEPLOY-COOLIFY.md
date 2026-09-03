# Deploying ERPNext / Frappe v16 on Coolify — delivery.kodatechnologies.co.tz

This stack runs the **official `frappe/erpnext:v16.34.1` image** for every
Frappe role. Nothing custom is built during deploy — there is no image build, so
no `bench get-app` / esbuild errors and no build-argument problems. You get a
clean, running Frappe foundation on your domain first, then install the custom
`delivery` app yourself from the terminal.

Services in `docker-compose.yml`: `frontend` (nginx, public), `websocket`,
`backend`, `queue-short`, `queue-long`, `scheduler`, a one-shot `configurator`,
`db` (MariaDB 11.8), `redis-cache`, `redis-queue`. Only `frontend` is exposed.

---

## 1. DNS (before TLS)

At your DNS provider for `kodatechnologies.co.tz`, create:

```
A   delivery   ->   <Coolify server public IP>
```

Verify: `dig +short delivery.kodatechnologies.co.tz` returns the server IP.

## 2. Server size

≥ **4 GB RAM** (8 GB recommended), 2 vCPU, 20 GB+ free disk.

## 3. Coolify resource = Docker Compose

1. New Resource → GitHub repo `BENETHNGOSWE/ORDER-DELIVERY-ERP`, branch `main`.
2. Deploy with **Docker Compose** (Coolify auto-detects `docker-compose.yml`).
   Do **not** use the Dockerfile build pack — the compose file does not build
   anything (the Dockerfile in the repo is unused/optional).

## 4. Environment variables

Resource → Environment Variables (Production). You only need:

```
DB_PASSWORD=<a long random password>
```

No build variables / tokens are needed (no image build happens).

## 5. Deploy

Click **Deploy**. Images are pulled, `db` becomes healthy, `configurator` runs
once and exits, then the services start. No site exists yet.

## 6. Point the domain at the FRONTEND service

1. Open the **frontend** service → Domains (or the app Domains).
2. Set:
   ```
   https://delivery.kodatechnologies.co.tz
   ```
   Container port: **8080**. Keep db / redis / workers unexposed.
3. Coolify requests the Let's Encrypt certificate automatically (DNS must
   resolve first). Redeploy once after saving.

## 7. Create the Frappe site (one time)

Open the **backend** service → **Terminal**:

```bash
bench new-site delivery.kodatechnologies.co.tz \
  --mariadb-root-password "$DB_PASSWORD" \
  --admin-password "YOUR_STRONG_ADMIN_PASSWORD"

bench --site delivery.kodatechnologies.co.tz clear-cache
```

Now https://delivery.kodatechnologies.co.tz opens ERPNext. The site name equals
the domain, which is how nginx routes requests.

## 8. Install the custom "delivery" app (after Frappe is up)

Still in the **backend** terminal. Because the GitHub repo folder
(`ORDER-DELIVERY-ERP`) differs from the Frappe app module name (`delivery`),
rename the cloned folder before installing (this avoids the esbuild crash):

```bash
bench get-app --skip-assets https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
rm -rf apps/delivery
mv apps/ORDER-DELIVERY-ERP apps/delivery
bench pip install -e apps/delivery
bench --site delivery.kodatechnologies.co.tz install-app delivery
bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

> Note: a runtime `bench get-app` lives in the **container layer**, not the
> persistent `sites` volume, so it must be repeated if a container is recreated
> (rebuild/upgrade). For a permanent, hands-off setup you can later bake the app
> into the image using the optional `Dockerfile` (it already contains the
> folder-rename fix) and switch the compose `image:` lines to your built image.
> Ask and I'll wire that up once the foundation is confirmed working.

The portal pages are plain HTML/CSS/JS under `www/delivery`, so they are served
fresh after clearing the website cache — no `bench build` is needed.

## 9. After setup

- Log in as `Administrator`, set currency/timezone.
- Create Merchants, Menu Items, Zones, Payment Methods.
- Home hero banners: Desk → **Home Banner** → New (image ~1600×520), Sort Order,
  Enabled, Save.

## Backups

Back up the **db-data** and **sites** volumes in Coolify. Logical backup from
the backend terminal:

```bash
bench --site delivery.kodatechnologies.co.tz backup --with-files
```

## Troubleshooting

- **`failed to read build-time.env ... "$host"`** → that came from the old
  Dockerfile build. The current compose builds nothing and has no `$host` env;
  make sure the resource uses **Docker Compose** and redeploy.
- **Site not found** → run step 7; site name must be `delivery.kodatechnologies.co.tz`.
- **TLS fails** → DNS not pointed yet, or ports 80/443 blocked. Verify `dig`.
- **esbuild / `paths[0] ... undefined` during get-app** → use `--skip-assets` and
  rename the folder as shown in step 8 (the repo folder ≠ module name).
