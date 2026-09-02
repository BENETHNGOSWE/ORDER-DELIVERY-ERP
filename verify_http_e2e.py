#!/usr/bin/env python3
"""
HTTP end-to-end verification of the Delivery & Logistics platform.

Drives the live server over HTTP exactly as the web portal and the future mobile
app do: session login per actor, then the full SRS workflow for each service.
Nothing here imports the app - it only speaks HTTP, so it proves the deployed
system works, not just the code.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
HOST = "logistics.test"
PASSWORD = "Sw!ftLog1stics26"

PASS, FAIL = [], []


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(label)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    return ok


class Client:
    """A logged-in browser/API session."""

    def __init__(self, name):
        self.name = name
        self.cookies = {}
        self.csrf = None

    def _req(self, method, path, data=None, raw=False):
        url = BASE + path
        body = None
        headers = {"Host": HOST, "Accept": "application/json"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if self.csrf:
            headers["X-Frappe-CSRF-Token"] = self.csrf
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode()
                status = r.status
                for h in r.headers.get_all("Set-Cookie") or []:
                    k, v = h.split(";", 1)[0].split("=", 1)
                    self.cookies[k] = v
        except urllib.error.HTTPError as e:
            text = e.read().decode()
            status = e.code
        if raw:
            return status, text
        try:
            return status, json.loads(text)
        except ValueError:
            return status, {"_raw": text[:400]}

    def login(self, user):
        st, res = self._req("POST", "/api/method/login",
                            {"usr": user, "pwd": PASSWORD})
        # Frappe serves the CSRF token inside any rendered page
        import re
        st2, page = self._req("GET", "/home", raw=True)
        m = re.search(r'csrf_token["\s:=]+([a-f0-9]{16,})', page)
        self.csrf = m.group(1) if m else None
        return st, res

    def call(self, endpoint, **kwargs):
        # `endpoint` (not `method`) because some APIs take a `method` argument
        # themselves - e.g. pay_transport(method="M-Pesa").
        st, res = self._req("POST", f"/api/method/{endpoint}", kwargs)
        if st != 200:
            msg = res.get("_server_messages") or res.get("exception") or res
            raise RuntimeError(f"{endpoint} -> HTTP {st}: {str(msg)[:300]}")
        return res.get("message")


def main():
    print("=" * 72)
    print("DELIVERY & LOGISTICS PLATFORM - HTTP END-TO-END VERIFICATION")
    print("=" * 72)

    # ------------------------------------------------------------------
    print("\n[1] Public catalogue & configuration (guest)")
    guest = Client("guest")
    cfg = guest.call("delivery.api.customer.platform_config")
    check("platform_config returns Swift Logistics / TZS",
          cfg["platform_name"] == "Swift Logistics" and cfg["currency"] == "TZS",
          f"{cfg['platform_name']} / {cfg['currency']}")
    check("payment methods include COD + M-Pesa + Tigo Pesa",
          set(["Cash On Delivery", "M-Pesa", "Tigo Pesa"]).issubset(set(cfg["payment_methods"])),
          ", ".join(cfg["payment_methods"]))

    merchants = guest.call("delivery.api.customer.list_merchants")
    check("merchants listed for guests", len(merchants) >= 3, f"{len(merchants)} merchants")

    # MRC-SWAHILI-GRILL is linked to merchant@demo.test in the demo data
    food = [m for m in merchants if m["name"] == "MRC-SWAHILI-GRILL"][0]
    cat = guest.call("delivery.api.customer.merchant_catalog", merchant=food["name"])
    check("merchant catalogue loads", len(cat["items"]) > 0, f"{len(cat['items'])} items")
    item = cat["items"][0]

    fee = guest.call("delivery.api.customer.quote_delivery_fee",
                     zone="Mikocheni", distance_km=5, items_total=20000)
    check("delivery fee quoted instantly", fee["delivery_fee"] > 0,
          f"fee={fee['delivery_fee']} {fee['currency']}")

    std = guest.call("delivery.api.customer.quote_parcel",
                     weight_kg=1.5, length_cm=30, width_cm=20, height_cm=15, distance_km=6)
    check("standard parcel bills instantly (no review)",
          std["needs_review"] is False and std["tariff_amount"] > 0,
          f"{std['weight_category']} = {std['tariff_amount']}")

    heavy = guest.call("delivery.api.customer.quote_parcel",
                       weight_kg=85, length_cm=90, width_cm=60, height_cm=60, distance_km=12)
    check("heavy parcel forced to manual review",
          heavy["needs_review"] is True and heavy["is_heavy"] is True,
          f"heavy={heavy['is_heavy']} oversized={heavy['is_oversized']}")

    tr = guest.call("delivery.api.customer.quote_transport",
                    stops=[{"address": "A", "distance_from_prev_km": 0},
                           {"address": "B", "distance_from_prev_km": 22},
                           {"address": "C", "distance_from_prev_km": 12}],
                    vehicle_type="Car", passengers=3)
    check("transport reference fare computed", tr["suggested_fare"] > 0,
          f"{tr['total_distance_km']} km -> {tr['suggested_fare']} {tr['currency']}")

    # ------------------------------------------------------------------
    print("\n[2] Food delivery: full SRS 3.1 lifecycle over HTTP")
    cust = Client("customer")
    st, res = cust.login("customer@demo.test")
    check("customer logs in", st == 200, f"HTTP {st}")

    order = cust.call("delivery.api.customer.place_order",
                      merchant=food["name"],
                      items=[{"item": item["name"], "qty": 2}],
                      delivery_address="Plot 12, Mikocheni, Dar es Salaam",
                      order_type="Food", delivery_zone="Mikocheni",
                      delivery_distance_km=5, payment_method="Cash On Delivery",
                      phone="+255700111222", customer_name="Amina Demo")
    ref = order["order"]
    check("order created and lands as PENDING", order["state"] == "PENDING", ref)
    check("order total computed in TZS",
          order["grand_total"] > 0 and order["currency"] == "TZS",
          f"{order['grand_total']} {order['currency']}")
    check("handoff OTP issued", bool(order["otp_code"]), f"OTP={order['otp_code']}")

    merch = Client("merchant")
    merch.login("merchant@demo.test")
    who = merch.call("delivery.api.merchant.whoami")
    check("merchant portal resolves its own vendor", who["merchant"] == food["name"],
          who["merchant"])
    inbox = merch.call("delivery.api.merchant.pending_orders")
    check("order visible in merchant inbox", any(o["name"] == ref for o in inbox),
          f"{len(inbox)} pending")
    acc = merch.call("delivery.api.merchant.accept_order", order=ref, prep_minutes=30)
    check("merchant accepts -> PREPARING with prep timer",
          acc["state"] == "PREPARING" and bool(acc["ready_at"]), f"ready_at={acc['ready_at']}")

    ops = Client("ops")
    ops.login("ops@demo.test")
    drv = ops.call("delivery.api.operations.available_drivers", service="Food")
    target = [d for d in drv if d["name"] == "DRV-001"][0]
    asg = ops.call("delivery.api.operations.assign_driver", reference=ref, driver=target["name"])
    check("operations assigns driver -> DRIVER_ASSIGNED",
          asg["state"] == "DRIVER_ASSIGNED", f"driver={asg['driver']}")

    drv_c = Client("driver")
    drv_c.login("driver@demo.test")
    jobs = drv_c.call("delivery.api.driver.my_jobs")
    check("job appears on driver dashboard", any(j["reference"] == ref for j in jobs),
          f"{len(jobs)} active jobs")
    pick = drv_c.call("delivery.api.driver.confirm_pickup", reference=ref)
    check("driver confirms pickup -> PICKED_UP", pick["state"] == "PICKED_UP")

    detail = drv_c.call("delivery.api.driver.job_detail", reference=ref)
    check("OTP required at handoff", detail["otp_required"] is True)

    bad = None
    try:
        drv_c.call("delivery.api.driver.complete_handoff", reference=ref, otp="0000")
    except RuntimeError as e:
        bad = str(e)
    check("wrong OTP is rejected", bad is not None and "OTP" in bad, (bad or "")[:80])

    done = drv_c.call("delivery.api.driver.complete_handoff",
                      reference=ref, otp=order["otp_code"], collected_amount=order["grand_total"])
    check("correct OTP completes delivery", done["state"] == "COMPLETED")
    check("COD settles to Paid at handoff", done["payment_status"] == "Paid",
          done["payment_status"])

    track = guest.call("delivery.api.customer.track", reference=ref)
    steps = [h["to"] for h in track["history"]]
    check("public tracking exposes full audit trail",
          steps == ["PENDING", "ACCEPTED", "PREPARING", "DRIVER_ASSIGNED", "PICKED_UP", "COMPLETED"],
          " -> ".join(steps))

    # ------------------------------------------------------------------
    print("\n[3] Parcel: instant billing vs manual tariff (SRS 3.2)")
    p_std = cust.call("delivery.api.customer.place_parcel_request",
                      pickup_address="Mikocheni B", dropoff_address="Masaki",
                      parcel_description="Sealed box of books", weight_kg=1.5,
                      length_cm=30, width_cm=20, height_cm=15, distance_km=6,
                      payment_method="Cash On Delivery", phone="+255700111222",
                      customer_name="Amina Demo")
    check("standard parcel instant-billed",
          p_std["needs_review"] is False and p_std["state"] == "REQUESTED",
          f"{p_std['parcel']} {p_std['weight_category']} = {p_std['tariff_amount']}")

    p_hvy = cust.call("delivery.api.customer.place_parcel_request",
                      pickup_address="Ubungo", dropoff_address="Kariakoo",
                      parcel_description="Generator set", weight_kg=85,
                      length_cm=90, width_cm=60, height_cm=60, distance_km=12,
                      phone="+255700111222", customer_name="Amina Demo")
    check("heavy parcel auto-routes to UNDER_REVIEW",
          p_hvy["state"] == "UNDER_REVIEW" and p_hvy["needs_review"] is True, p_hvy["parcel"])

    queue = ops.call("delivery.api.operations.review_queue")
    check("parcel appears in operations review queue",
          any(p["name"] == p_hvy["parcel"] for p in queue["parcels"]),
          f"{queue['counts']['parcels']} awaiting review")

    tariff = ops.call("delivery.api.operations.set_parcel_tariff",
                      reference=p_hvy["parcel"], amount=75000, note="Two-person lift")
    check("operations sets manual tariff -> PRICE_AGREED",
          tariff["state"] == "PRICE_AGREED" and tariff["tariff_amount"] == 75000,
          f"{tariff['tariff_amount']} {tariff['currency']}")

    # ------------------------------------------------------------------
    print("\n[4] Transport: negotiated multi-stop (SRS 3.3)")
    t = cust.call("delivery.api.customer.place_transport_request",
                  stops=[{"idx_label": "Home", "address": "Mbezi Beach",
                          "stop_type": "Pickup", "distance_from_prev_km": 0},
                         {"idx_label": "Airport", "address": "JNIA, Dar es Salaam",
                          "stop_type": "Waypoint", "distance_from_prev_km": 22},
                         {"idx_label": "Office", "address": "Masaki, Dar es Salaam",
                          "stop_type": "Drop-off", "distance_from_prev_km": 12}],
                  trip_type="Passenger", vehicle_type="Car", passengers=3,
                  luggage_pieces=3, phone="+255700111222",
                  special_requirements="Airport pickup board",
                  customer_name="Amina Demo")
    tref = t["request"]
    import re as _re
    check("reference ID matches TR-YYYY-NNNN",
          bool(_re.match(r"^TR-\d{4}-\d{4}$", tref)), tref)
    check("transport starts UNDER_REVIEW (staff must review)",
          t["state"] == "UNDER_REVIEW", t["state"])
    check("route distance summed across stops",
          abs(t["total_distance_km"] - 34.0) < 0.01, f"{t['total_distance_km']} km")

    blocked = None
    try:
        cust.call("delivery.api.customer.pay_transport", reference=tref, method="M-Pesa")
    except RuntimeError as e:
        blocked = str(e)
    check("payment blocked before a fare is agreed", blocked is not None, (blocked or "")[:80])

    det = ops.call("delivery.api.operations.transport_detail", reference=tref)
    check("operations sees the full itinerary", len(det["stops"]) == 3,
          f"{len(det['stops'])} stops, phone {det['customer_phone']}")

    ops.call("delivery.api.operations.record_contact", reference=tref,
             note="Called customer; confirmed 3 pax + 3 bags, 6am airport")
    agreed = ops.call("delivery.api.operations.log_agreed_price",
                      reference=tref, price=68000, note="Agreed incl. waiting time")
    check("agreed price logged -> PRICE_AGREED",
          agreed["state"] == "PRICE_AGREED" and agreed["agreed_price"] == 68000,
          f"{agreed['agreed_price']} {agreed['currency']}")
    check("quote carries a validity window", bool(agreed["quote_expires_on"]),
          agreed["quote_expires_on"])

    ttrack = guest.call("delivery.api.customer.track", reference=tref)
    check("customer sees the agreed quote on their dashboard",
          ttrack["agreed_price"] == 68000, f"{ttrack['agreed_price']} {ttrack['currency']}")

    appr = cust.call("delivery.api.customer.approve_transport_quote", reference=tref)
    check("customer approves the quote -> ACCEPTED", appr["state"] == "ACCEPTED")

    pay = cust.call("delivery.api.customer.pay_transport",
                    reference=tref, method="M-Pesa", phone="+255700111222")
    check("M-Pesa checkout succeeds (sandbox simulator)",
          pay["status"] == "Paid" and pay["reference"], f"txn={pay['reference']}")

    td = ops.call("delivery.api.operations.available_drivers", service="Transport")
    tdrv = [d for d in td if d["name"] == "DRV-002"][0]
    tasg = ops.call("delivery.api.operations.assign_driver", reference=tref, driver=tdrv["name"])
    check("driver assigned to trip", tasg["state"] == "DRIVER_ASSIGNED", tasg["driver"])

    d2 = Client("driver2")
    d2.login("driver2@demo.test")
    tstart = d2.call("delivery.api.driver.confirm_pickup", reference=tref)
    check("trip starts -> PICKED_UP (Route Active)", tstart["state"] == "PICKED_UP")
    adv = d2.call("delivery.api.driver.advance_transport_stop", reference=tref)
    check("driver advances the itinerary",
          adv["current_stop"] == 1 and adv["total_stops"] == 3,
          f"stop {adv['current_stop']}/{adv['total_stops']}")

    # ------------------------------------------------------------------
    print("\n[5] Dashboards & security")
    dash = ops.call("delivery.api.operations.dashboard")
    check("operations dashboard aggregates all services",
          dash["orders"]["total"] >= 1 and dash["parcels"]["total"] >= 2
          and dash["transport"]["total"] >= 1,
          f"orders={dash['orders']['total']} parcels={dash['parcels']['total']} "
          f"transport={dash['transport']['total']}")
    check("revenue reported in TZS", dash["currency"] == "TZS", dash["currency"])

    mine = cust.call("delivery.api.customer.my_orders")
    check("customer dashboard lists their orders", len(mine) >= 1, f"{len(mine)} orders")
    myt = cust.call("delivery.api.customer.my_transport")
    check("customer sees agreed pricing", any(x["agreed_price"] == 68000 for x in myt))

    denied = None
    try:
        cust.call("delivery.api.operations.dashboard")
    except RuntimeError as e:
        denied = str(e)
    check("customer cannot open the operations console",
          denied is not None and "Operations access required" in denied, (denied or "")[:70])

    denied2 = None
    try:
        merch.call("delivery.api.merchant.catalog", merchant="MRC-KARIAKOO-MART")
    except RuntimeError as e:
        denied2 = str(e)
    check("merchant cannot read another merchant's catalogue",
          denied2 is not None and "do not manage" in denied2, (denied2 or "")[:70])

    anon = Client("anon")
    denied3 = None
    try:
        anon.call("delivery.api.customer.place_order", merchant=food["name"],
                  items=[{"item": item["name"], "qty": 1}], delivery_address="x")
    except RuntimeError as e:
        denied3 = str(e)
    check("guest cannot place an order", denied3 is not None, (denied3 or "")[:70])

    earn = d2.call("delivery.api.driver.my_earnings")
    check("driver earnings endpoint responds", isinstance(earn, dict),
          f"{sum(len(v) for v in earn.values())} rows")

    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for f in FAIL:
            print("  -", f)
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
