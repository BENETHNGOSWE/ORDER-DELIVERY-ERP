# Deploying to Coolify — delivery.kodatechnologies.co.tz

ERPNext/Frappe v16 runs as a **Docker Compose stack** (not a single Dockerfile
app). The repo ships:

- `Dockerfile` — builds the `delivery` app on top of the official **frappe/erpnext:v16.34.1**
  image. The SAME image runs every role (frontend/backend/workers/scheduler/websocket).
- `docker-compose.yml` — the full stack: frontend (nginx), websocket, backend,
  queue-short, queue-long, scheduler, a one-shot **configurator**, MariaDB 11.8,
  and two Redis containers.

> The image tag is already pinned to **v16.34.1**. You do not need to change it.

---

## 0. Why the first build failed

You created the resource with **Build Pack = Dockerfile**. That builds ONE
container, but ERPNext needs the whole Compose stack, and a single-container
build cannot serve on its own. You must deploy the resource as a
**Docker Compose** application (see step 3).

---

## 1. DNS

At your DNS provider for `kodatechnologies.co.tz`, create:

```
A   delivery   ->   <Coolify server public IP>
```

Verify before deploying TLS:

```bash
dig +short delivery.kodatechnologies.co.tz
```

It must return the Coolify server IP.

## 2. Server resources

≥ **4 GB RAM** (8 GB recommended), 2 vCPU, 20 GB+ disk.

## 3. Create the resource as Docker Compose (not Dockerfile)

In Coolify:

1. **New Resource** → your GitHub repo `BENETHNGOSWE/ORDER-DELIVERY-ERP` (branch `main`).
2. When asked for the build/resource type, choose **Docker Compose** (Coolify
   auto-detects `docker-compose.yml` in the repo root).
   - If you already created it with **Build Pack = Dockerfile**, open the
     resource → **Configuration → General → Build Pack** and switch it to
     **Docker Compose**, then Save. (Deleting and re-adding the resource as a
     Compose app is the safest route.)
3. Coolify will detect the services. Only **frontend** will be public.

## 4. Environment variables (Production)

On the resource → **Environment Variables**, add:

```
DB_PASSWORD=<a long random secret>
```

If the repo is **private**, also add a **Build Variable**:

```
GIT_TOKEN=<a GitHub PAT with repo read>
```
(Public repo → skip. The Dockerfile uses it for `bench get-app`.)

## 5. First deploy

Click **Deploy**. The image builds on top of `frappe/erpnext:v16.34.1` (this
takes several minutes the first time), then `configurator` runs once, MariaDB
becomes healthy, and the services start. No site exists yet — the app won’t
answer properly until step 6.

## 6. Create the site + install the app (one time)

Open the **backend** service → **Terminal** (Execute Command) and run:

```bash
bench new-site delivery.kodatechnologies.co.tz \
  --mariadb-root-password "$DB_PASSWORD" \
  --admin-password "YOUR_STRONG_ADMIN_PASSWORD"

bench --site delivery.kodatechnologies.co.tz install-app delivery
bench --site delivery.kodatechnologies.co.tz clear-cache
bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

The `delivery` app is already inside the image; `install-app` installs it into
this site and runs migrations (creates the **Home Banner** doctype, etc.).
Data/files live on persistent volumes and survive redeploys.

## 7. Point the domain at the FRONTEND service

1. In Coolify open the **frontend** service (or the app → Domains).
2. Add the domain and make sure it routes to the **frontend** service on
   container port **8080** (the Frappe nginx entrypoint listens on 8080).
   ```
   https://delivery.kodatechnologies.co.tz
   ```
3. Coolify requests a Let’s Encrypt certificate automatically (DNS must resolve
   first). Redeploy once after saving.
4. Leave db/redis/workers/scheduler **unexposed** (internal only).

Visit **https://delivery.kodatechnologies.co.tz** → login; customer portal at
**/delivery**.

## 8. After setup

- Log in as `Administrator`, set currency/timezone.
- Create Merchants, Menu Items, Zones, Payment Methods.
- Upload banners: Desk → **Home Banner** → New → image (~1600×520), Sort Order,
  Enabled, Save → they appear in the home carousel.

## Backups

Back up the **db-data** and **sites** volumes (Coolify → Backups). Logical
backup from the **backend** terminal:

```bash
bench --site delivery.kodatechnologies.co.tz backup --with-files
```

## Updating after pushing code

1. Push to `main`.
2. Coolify → **Redeploy** (rebuilds the image with the new code).
3. After deploy, in the **backend** terminal:
   ```bash
   bench --site delivery.kodatechnologies.co.tz migrate
   bench --site delivery.kodatechnologies.co.tz clear-cache
   bench --site delivery.kodatechnologies.co.tz clear-website-cache
   ```

## Troubleshooting

- **frappe/erpnext:v16.x: not found** → you’re on an older build; the tag is now
  pinned to v16.34.1. Pull the latest `main` and make sure the resource uses
  **Docker Compose**.
- **Site not found** → run step 6; the site name must equal the host
  `delivery.kodatechnologies.co.tz`.
- **TLS fails** → DNS not pointed yet, or ports 80/443 blocked. Verify `dig`.
- **Workers/scheduler idle** → they share the `sites` volume and resolve the
  site by host; ensure the domain hits the frontend and, if needed, set
  `FRAPPE_SITE_NAME_HEADER=delivery.kodatechnologies.co.tz`.
- **Private repo build fails** → add the `GIT_TOKEN` build variable.
