# ERPNext / Frappe v16 on Coolify — delivery.kodatechnologies.co.tz

**Permanent-app edition:** every Frappe service builds the repo `Dockerfile`
(official `frappe/erpnext:v16.34.1` **+ the custom `delivery` app baked in**).
A deploy of `main` always ships with the app installed — **no manual
get-app / install-app after updates, ever.**

Data (database, uploaded files, site config) lives in named volumes —
`mariadb-data`, `sites`, `redis-queue-data` — **not** in the image, so
redeploys and container recreations never touch it.

---

## 1. DNS
Create an A record at your registrar: `delivery -> <Coolify server public IP>`.
Verify: `dig +short delivery.kodatechnologies.co.tz`.

## 2. Deploy in Coolify
- Resource → GitHub repo `BENETHNGOSWE/ORDER-DELIVERY-ERP`, branch `main`,
  type **Docker Compose** (Coolify uses the repo's `docker-compose.yml`).
- Make sure no old variables with a `$` remain in the Environment Variables
  box — delete them.
- **Save & Deploy.** The first build compiles the custom image (~2–5 min).
  Later deploys are faster (Docker layer cache). Wait for `mariadb` healthy
  and all 8 containers up (`docker ps`).

## 3. Point the domain to FRONTEND
- In Coolify open the **frontend** service → domain:
  `https://delivery.kodatechnologies.co.tz`, port **8080**.
- Leave mariadb/redis/backend/etc. unexposed. Let's Encrypt is automatic once
  DNS resolves.

## 4. Create the site (first deployment only)
Open the **backend** service → Terminal:

```bash
bench new-site delivery.kodatechnologies.co.tz \
  --db-host mariadb \
  --mariadb-root-password KodaDelivery2026Secure
# (set the Administrator password when prompted)

bench --site delivery.kodatechnologies.co.tz install-app erpnext
bench --site delivery.kodatechnologies.co.tz install-app delivery
bench --site delivery.kodatechnologies.co.tz enable-scheduler
bench --site delivery.kodatechnologies.co.tz set-admin-password YOURADMINPASS
```

The site name MUST equal the domain (`FRAPPE_SITE_NAME_HEADER` is set to it).
The `delivery` app code is already in the image — `install-app` just links it
to the site. (On the current server this step is already done: the site and
its data survive in volumes, so after adopting the custom image you do NOT
run this again.)

## 5. Everyday updates — just deploy
```bash
git pull            # on your working copy
# ...make changes, commit...
git push            # to GitHub main
```
Then in Coolify: **Deploy**. That's it. The image is rebuilt with your new
app code; containers are recreated; the site comes back with data intact.
No terminal steps. If a page looks stale in the browser, hard-refresh
(Ctrl+Shift+R).

## 6. Data safety — read this once
- ✅ **Deploy / Redeploy / Restart** in Coolify: always safe. Volumes persist.
- ✅ Container recreation (e.g. server reboot, `docker restart`): safe.
- ⚠️ **Never** delete the resource **with** its volumes, or run
  `docker volume rm`, unless you intend to erase all data.
- 📦 Backups: periodically dump the DB from the backend terminal:
  ```bash
  bench --site delivery.kodatechnologies.co.tz backup --with-files
  ```
  and copy `sites/backups/` (or the `mariadb-data` volume) somewhere off-server.

## 7. How the app is baked in (reference)
- `Dockerfile`: copies `delivery/` + `pyproject.toml` into
  `/home/frappe/frappe-bench/apps/delivery`, runs
  `bench pip install -e apps/delivery`, and pre-places portal assets in
  `/usr/share/nginx/html/assets/delivery` (nginx) + `/opt/delivery-assets`
  (staging).
- `docker/dl-entrypoint.sh`: runs before every service, refreshes
  `sites/apps.txt` and `sites/assets/delivery` in the shared volume, then
  execs the stock entrypoint.
- To upgrade Frappe/ERPNext later: bump the `FROM` line and the
  `image:` tag in `docker-compose.yml` together (e.g. `v16.35.x`), deploy,
  then run `bench --site <site> migrate` once from the backend terminal.

## Admin / troubleshooting
- Reset admin password:
  `bench --site delivery.kodatechnologies.co.tz set-admin-password NEWPASS`
- Logs: `docker logs <frontend|backend|scheduler|worker|...>` (use the
  container names with this project's prefix).
- **Emergency fallback** (only if the build itself is broken and you need the
  site up on the old official-image compose): checkout the previous compose
  (`git revert`), deploy, then reinstall the app at runtime:
  ```bash
  bench get-app --skip-assets https://github.com/BENETHNGOSWE/ORDER-DELIVERY-ERP.git
  # v16 names the folder apps/delivery itself; then:
  bench pip install -e apps/delivery
  ls -1 apps > sites/apps.txt
  bench --site delivery.kodatechnologies.co.tz install-app delivery
  bench --site delivery.kodatechnologies.co.tz clear-cache
  ```
