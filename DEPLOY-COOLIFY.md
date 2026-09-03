# Deploying to Coolify — delivery.kodatechnologies.co.tz

This project is an **ERPNext / Frappe v16 application** (not a single-process web
app). It runs as a **Docker Compose stack** with: nginx (frontend), websocket,
backend + 3 background workers + scheduler, MariaDB, and three Redis servers.

The files in this repo make that one-click deployable in Coolify:

- `Dockerfile` — builds the `delivery` app on top of the official ERPNext image
  (used by backend/workers/scheduler).
- `docker-compose.yml` — the full stack.
- `.env.production.example` — variables you set in Coolify.

> ⚠️ **Before the first deploy:** open `docker-compose.yml` and `Dockerfile` and
> replace every `v16.x` image tag with the exact newest **v16** tag from
> <https://hub.docker.com/r/frappe/erpnext/tags> (e.g. `v16.x.y`). All services
> must use the **same** tag. Commit the change.

---

## 1. DNS (do this first)

At your domain registrar / DNS provider for `kodatechnologies.co.tz`, create:

```
A   delivery   ->   <your Coolify server public IP>
```

Wait until it resolves (check from your laptop):

```bash
dig +short delivery.kodatechnologies.co.tz
# or: nslookup delivery.kodatechnologies.co.tz
```

It must return the Coolify server IP before Coolify can issue the HTTPS cert.

---

## 2. Server resources

Frappe needs room. On the Coolify **server** ensure roughly:

- **4 GB RAM minimum** (8 GB recommended), 2+ vCPU
- 20+ GB free disk

In Coolify: **Server → Settings**, confirm Docker is healthy and there is free
memory/disk.

---

## 3. Add the GitHub repository to Coolify

1. Coolify dashboard → **New Resource** → **Private Repository (with GitHub App)**
   or **Public Repository**.
2. Your GitHub App is already connected — select the repo
   `BENETHNGOSWE/ORDER-DELIVERY-ERP`.
3. **Important — choose the resource type as “Docker Compose”** (Coolify normally
   auto-detects `docker-compose.yml`). Do **not** use “Dockerfile” / buildpack —
   this stack is multi-service.
4. Branch: `main`. Base directory: repo root (where `docker-compose.yml` is).

Coolify will detect services: `frontend`, `websocket`, `backend`,
`queue-default/short/long`, `scheduler`, `mariadb`, `redis-*`.

---

## 4. Environment variables

Open the resource → **Environment Variables**, add (Production):

```
MYSQL_ROOT_PASSWORD=<a long random secret>
```

(Only this is required for the first boot. `SITE_NAME` / `ADMIN_PASSWORD` are set
in step 6.)

If the GitHub repo is **private**, add a **Build Variable** (not runtime):

```
GIT_TOKEN=<a GitHub PAT with repo read>
```

so the `Dockerfile` can `bench get-app` the private repo. If the repo is public
you can skip this.

---

## 5. First deploy

Click **Deploy**. Coolify builds the custom image and starts every service.
Watch the logs — wait until `mariadb` reports healthy and `backend` is running.

No site exists yet, so the web app won’t answer properly — that’s expected.

---

## 6. Create the site + install the delivery app (one time)

In Coolify, open the **backend** service → **Terminal** (or “Execute Command”),
and run:

```bash
# create the site (uses the domain as the site name)
bench new-site delivery.kodatechnologies.co.tz \
  --mariadb-root-password "$MYSQL_ROOT_PASSWORD" \
  --admin-password "YOUR_STRONG_ADMIN_PASSWORD"

# install the custom Delivery Logistics app into the site
bench --site delivery.kodatechnologies.co.tz install-app delivery

# confirm settings + clear caches
bench --site delivery.kodatechnologies.co.tz set-config -p hosted_user Administrator
bench --site delivery.kodatechnologies.co.tz clear-cache
bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

Notes:

- The `delivery` app is already **in the image** (fetched at build), so
  `install-app` just installs it into this site and runs migrations (this creates
  the **Home Banner** doctype etc.).
- Files/DB are on persistent volumes, so this survives redeploys.

Then, back in Coolify **Environment Variables**, add for the workers/scheduler:

```
SITE_NAME=delivery.kodatechnologies.co.tz
```

and **Redeploy** (or restart the backend/worker/scheduler services) so background
jobs know which site to run.

---

## 7. Connect the domain (HTTPS)

1. Coolify resource → the **frontend** service → **Domains**.
2. Add:
   ```
   https://delivery.kodatechnologies.co.tz
   ```
   Coolify generates the reverse-proxy config and requests a **Let’s Encrypt**
   certificate automatically.
3. Make sure the service **port is `80`** (the frappe-nginx container listens on
   port 80). Do **not** expose mariadb/redis/workers publicly.
4. Redeploy once so the proxy picks up the domain.

Visit **https://delivery.kodatechnologies.co.tz** → you should get the ERPNext
login and the customer portal at **/delivery**.

---

## 8. Post-setup checklist

- Log in as `Administrator` with the admin password you set.
- Set system currency/timezone (Setup).
- Create your **Merchants**, **Menu Items**, **Zones**, **Payment Methods**,
  and **Home Banners** (Desk → search the doctype names).
- Add banner images: Desk → **Home Banner** → New → upload (recommended
  ~1600×520 px), set Sort Order, enable, Save. They appear in the home carousel.

---

## Backups (important)

Back up the two things that matter (Coolify → Backups, or cron + restic/rsync):

- the **MariaDB** volume (`db-data`)
- the **sites** volume (`sites-vol`) — uploaded images/files live here

A minimal logical backup you can run from the backend container:

```bash
bench --site delivery.kodatechnologies.co.tz backup --with-files
```

Store the generated files off-server.

---

## Updating after you push new code

The custom app is built into the image, so:

1. Push changes to GitHub (`main`).
2. In Coolify click **Redeploy** (it rebuilds the image with the latest code).
3. After the deploy, in the **backend** terminal run:
   ```bash
   bench --site delivery.kodatechnologies.co.tz migrate
   bench --site delivery.kodatechnologies.co.tz clear-cache
   bench --site delivery.kodatechnologies.co.tz clear-website-cache
   ```
   (Only needed when doctypes/schema changed. Portal HTML/CSS/JS changes just
   need the caches cleared.)

---

## Troubleshooting

- **No site / “Site not found”** → you skipped step 6, or `SITE_NAME` doesn’t
  match the domain. Site name must equal the public host
  (`delivery.kodatechnologies.co.tz`).
- **TLS cert fails** → DNS A record not pointing at the server yet, or port
  80/443 not open. Verify `dig` and the server firewall / security group.
- **Workers do nothing / scheduled jobs stuck** → set `SITE_NAME` env and restart
  backend/worker/scheduler.
- **Image pull fails on `v16.x`** → replace the placeholder tags with a real v16
  tag (see the note at the top).
- **Private repo build fails** → add the `GIT_TOKEN` build variable.
