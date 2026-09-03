# ERPNext / Frappe v16 on Coolify — delivery.kodatechnologies.co.tz

Proven Coolify layout: the official **`frappe/erpnext:v16.34.1`** image for every
role, with the database/Redis set as **literal environment variables** on each
service. There is **no image build and no `$host` variable**, so Coolify deploys
cleanly. Only `frontend` is public (port **8080**).

Containers: `frontend` (nginx), `backend` (gunicorn), `websocket`, `scheduler`,
`worker`, `mariadb` (10.6), `redis-cache`, `redis-queue`.

> The DB root password is set in the compose file (`KodaDelivery2026Secure`).
> Change it if you wish, but it must be the same in every service. You do NOT
> need to add any variables in the Coolify Environment Variables UI.

---

## 1. DNS
Create an A record at your registrar: `delivery -> <Coolify server public IP>`.
Verify: `dig +short delivery.kodatechnologies.co.tz`.

## 2. Deploy in Coolify
- New Resource → GitHub repo `BENETHNGOSWE/ORDER-DELIVERY-ERP`, branch `main`.
- Choose **Docker Compose** (Coolify uses the repo's `docker-compose.yml`).
- Make sure no old variables with a `$` (e.g. a previous `$host`) remain in the
  Environment Variables box — delete them.
- **Save & Deploy.** Wait ~2–3 min for images to pull and `mariadb` to become
  healthy (`docker ps` on the server shows all 8 containers).

## 3. Point the domain to FRONTEND
- In Coolify open the **frontend** service → set the domain:
  `https://delivery.kodatechnologies.co.tz`, service port **8080**.
- Leave mariadb/redis/backend/etc. unexposed. Coolify issues the Let's Encrypt
  certificate automatically (DNS must resolve first).

## 4. Create the site (backend terminal)
Open the **backend** service → Terminal:

```bash
bench new-site delivery.kodatechnologies.co.tz \
  --db-host mariadb \
  --mariadb-root-password KodaDelivery2026Secure
# (set the Administrator password when prompted)

bench --site delivery.kodatechnologies.co.tz install-app erpnext
bench --site delivery.kodatechnologies.co.tz enable-scheduler
```

The site name MUST equal the domain (`delivery.kodatechnologies.co.tz`) because
`FRAPPE_SITE_NAME_HEADER` is set to it. https://delivery.kodatechnologies.co.tz
now opens ERPNext.

## 5. Install the custom "delivery" app
Still in the **backend** terminal. Rename the cloned repo folder to match the
module name (`delivery`) to avoid the esbuild build error:

```bash
bench get-app --skip-assets https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
rm -rf apps/delivery
mv apps/ORDER-DELIVERY-ERP apps/delivery
bench pip install -e apps/delivery
bench --site delivery.kodatechnologies.co.tz install-app delivery
bench --site delivery.kodatechnologies.co.tz clear-website-cache
```

Your customer portal is at **/delivery**. Upload home banners via Desk →
**Home Banner**.

> Runtime `get-app` lives in the container layer; re-run step 5 if a container is
> recreated. Once the site is confirmed working we can bake the app into a
> custom image so it persists automatically (ask when ready).

## Admin / troubleshooting
- Reset admin password:
  `bench --site delivery.kodatechnologies.co.tz set-admin-password NEWPASS`
- If login shows a server/redis error, verify config from the backend terminal:
  ```
  bench set-config -g redis_cache "redis://redis-cache:6379"
  bench set-config -g redis_queue "redis://redis-queue:6379"
  bench set-config -g redis_socketio "redis://redis-queue:6379"
  bench set-config -g db_host mariadb
  ```
  (Redis hostnames are the short service names `redis-cache` / `redis-queue` in
  this compose — adjust if your Coolify prefixes service names.)
- Logs: `docker logs <frontend|backend|scheduler|worker>`.
- Backups: back up the `mariadb-data` and `sites` volumes in Coolify.
