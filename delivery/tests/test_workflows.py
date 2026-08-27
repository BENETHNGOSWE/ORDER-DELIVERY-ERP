"""
End-to-end workflow tests for all four services, plus the security boundaries.

These drive the real documents through the real controllers, so they cover the
path a portal request takes - not just the fee maths.
"""
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from delivery.api import customer, driver as driver_api, merchant, operations
from delivery.demo_data import PASSWORD, seed
from delivery.tests._helpers import _driver_for, _item, _merchant

CUSTOMER = "customer@demo.test"
MERCHANT_1 = "merchant@demo.test"
MERCHANT_2 = "merchant2@demo.test"
OPS = "ops@demo.test"
DRIVER_1 = "driver@demo.test"
DRIVER_2 = "driver2@demo.test"


class TestWorkflows(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed()

    # -- helpers ----------------------------------------------------------
    def _place_food(self):
        frappe.set_user(CUSTOMER)
        shop = _merchant("Food", user=MERCHANT_1)
        items = _item(shop, 2)
        return customer.place_order(
            merchant=shop,
            items=[{"item": i.name, "qty": 2} for i in items],
            delivery_address="Plot 12, Masaki, Dar es Salaam",
            order_type="Food",
            payment_method="Cash On Delivery",
            phone="+255700111222"), items

    # ---------------------------------------------------------------- food
    def test_food_order_starts_pending_with_an_otp(self):
        result, _ = self._place_food()
        self.assertEqual(result["state"], "PENDING")
        self.assertRegex(str(result["otp_code"]), r"^\d{4}$")
        self.assertGreater(result["grand_total"], 0)

    def test_order_total_is_in_the_platform_currency(self):
        result, _ = self._place_food()
        self.assertEqual(result["currency"],
                         frappe.get_cached_doc("Logistics Settings").currency)

    def test_merchant_sees_the_order_in_its_inbox(self):
        result, _ = self._place_food()
        frappe.set_user(MERCHANT_1)
        inbox = [o["name"] for o in merchant.pending_orders()]
        self.assertIn(result["order"], inbox)

    def test_merchant_acceptance_starts_the_prep_timer(self):
        result, _ = self._place_food()
        frappe.set_user(MERCHANT_1)
        accepted = merchant.accept_order(result["order"], prep_minutes=30)
        self.assertEqual(accepted["state"], "PREPARING")
        self.assertEqual(accepted["prep_minutes"], 30)
        self.assertTrue(accepted["ready_at"])

    def test_full_food_lifecycle_to_completed(self):
        result, _ = self._place_food()
        ref = result["order"]
        otp = result["otp_code"]

        frappe.set_user(MERCHANT_1)
        merchant.accept_order(ref, prep_minutes=20)

        frappe.set_user(OPS)
        drv = _driver_for(DRIVER_1, "can_food")
        operations.assign_driver(ref, drv)
        self.assertEqual(frappe.db.get_value("Delivery Order", ref,
                                             "workflow_state"), "DRIVER_ASSIGNED")

        frappe.set_user(DRIVER_1)
        jobs = [j["reference"] for j in driver_api.my_jobs()]
        self.assertIn(ref, jobs)

        driver_api.confirm_pickup(ref)
        self.assertEqual(frappe.db.get_value("Delivery Order", ref,
                                             "workflow_state"), "PICKED_UP")

        done = driver_api.complete_handoff(ref, otp=otp, collected_amount=50000)
        self.assertEqual(done["state"], "COMPLETED")
        # Cash On Delivery settles at the handoff
        self.assertEqual(frappe.db.get_value("Delivery Order", ref,
                                             "payment_status"), "Paid")

    def test_wrong_otp_is_rejected(self):
        result, _ = self._place_food()
        ref = result["order"]

        frappe.set_user(MERCHANT_1)
        merchant.accept_order(ref, prep_minutes=15)
        frappe.set_user(OPS)
        operations.assign_driver(ref, _driver_for(DRIVER_1, "can_food"))

        frappe.set_user(DRIVER_1)
        driver_api.confirm_pickup(ref)
        wrong = "{0:04d}".format((int(result["otp_code"]) + 1) % 10000)
        with self.assertRaises(frappe.ValidationError):
            driver_api.complete_handoff(ref, otp=wrong, collected_amount=10000)

    def test_public_tracking_exposes_the_audit_trail(self):
        result, _ = self._place_food()
        frappe.set_user("Guest")
        tracked = customer.track(result["order"])
        self.assertEqual(tracked["reference"], result["order"])
        states = [t["state"] for t in tracked["timeline"]]
        self.assertIn("PENDING", states)

    # -------------------------------------------------------------- parcel
    def test_standard_parcel_is_billed_instantly(self):
        frappe.set_user(CUSTOMER)
        r = customer.place_parcel_request(
            pickup_address="Masaki, Dar es Salaam",
            dropoff_address="Kariakoo, Dar es Salaam",
            parcel_description="Documents", weight_kg=1.5,
            distance_km=5, payment_method="Cash On Delivery",
            phone="+255700111222")
        self.assertFalse(r["needs_review"])
        self.assertEqual(r["state"], "PRICE_AGREED")
        self.assertGreater(r["tariff_amount"], 0)

    def test_heavy_parcel_goes_to_manual_review(self):
        frappe.set_user(CUSTOMER)
        r = customer.place_parcel_request(
            pickup_address="Masaki, Dar es Salaam",
            dropoff_address="Mbezi, Dar es Salaam",
            parcel_description="Machine part", weight_kg=85,
            distance_km=18, payment_method="Cash On Delivery",
            phone="+255700111222")
        self.assertTrue(r["needs_review"])
        self.assertEqual(r["state"], "UNDER_REVIEW")

    def test_operations_sets_the_manual_tariff(self):
        frappe.set_user(CUSTOMER)
        r = customer.place_parcel_request(
            pickup_address="Masaki", dropoff_address="Mbezi",
            parcel_description="Oversized crate", weight_kg=85,
            distance_km=18, payment_method="Cash On Delivery",
            phone="+255700111222")

        frappe.set_user(OPS)
        queue = [p["name"] for p in operations.review_queue()["parcels"]]
        self.assertIn(r["parcel"], queue)

        priced = operations.set_parcel_tariff(r["parcel"], 75000, "Agreed by phone")
        self.assertEqual(priced["state"], "PRICE_AGREED")
        self.assertEqual(priced["tariff_amount"], 75000)

    # ----------------------------------------------------------- transport
    def _place_transport(self):
        frappe.set_user(CUSTOMER)
        stops = [
            {"idx_label": "Origin", "address": "Masaki", "stop_type": "Pickup",
             "distance_from_prev_km": 0},
            {"idx_label": "Waypoint", "address": "Kariakoo", "stop_type": "Waypoint",
             "distance_from_prev_km": 12},
            {"idx_label": "Destination", "address": "Mbezi", "stop_type": "Drop-off",
             "distance_from_prev_km": 22},
        ]
        return customer.place_transport_request(
            stops=stops, trip_type="Passenger", vehicle_type="Van",
            passengers=3, phone="+255700111222")

    def test_transport_reference_format(self):
        r = self._place_transport()
        self.assertRegex(r["request"], r"^TR-\d{4}-\d{4}$")

    def test_transport_starts_under_review(self):
        r = self._place_transport()
        self.assertEqual(r["state"], "UNDER_REVIEW")

    def test_route_distance_is_summed(self):
        r = self._place_transport()
        self.assertEqual(flt(r["total_distance_km"]), 34.0)

    def test_payment_is_blocked_before_a_fare_is_agreed(self):
        r = self._place_transport()
        with self.assertRaises(frappe.ValidationError):
            customer.pay_transport(r["request"], method="M-Pesa")

    def test_full_negotiated_transport_lifecycle(self):
        r = self._place_transport()
        ref = r["request"]

        frappe.set_user(OPS)
        detail = operations.transport_detail(ref)
        self.assertEqual(len(detail["stops"]), 3)
        self.assertEqual(detail["customer_phone"], "+255700111222")

        agreed = operations.log_agreed_price(ref, 68000, "Agreed by phone")
        self.assertEqual(agreed["state"], "PRICE_AGREED")
        self.assertEqual(agreed["agreed_price"], 68000)
        self.assertTrue(agreed["quote_expires_on"])

        frappe.set_user(CUSTOMER)
        approved = customer.approve_transport_quote(ref)
        self.assertEqual(approved["state"], "ACCEPTED")
        paid = customer.pay_transport(ref, method="M-Pesa", phone="+255700111222")
        self.assertEqual(paid["payment_status"], "Paid")

        frappe.set_user(OPS)
        drv = _driver_for(DRIVER_2, "can_transport")
        operations.assign_driver(ref, drv)

        frappe.set_user(DRIVER_2)
        driver_api.confirm_pickup(ref)
        self.assertEqual(frappe.db.get_value("Transport Request", ref,
                                             "workflow_state"), "PICKED_UP")

        step = driver_api.advance_transport_stop(ref)
        self.assertEqual(step["stop"], 1)
        self.assertEqual(step["total_stops"], 3)

    def test_transport_needs_at_least_two_stops(self):
        frappe.set_user(CUSTOMER)
        with self.assertRaises(frappe.ValidationError):
            customer.place_transport_request(
                stops=[{"address": "Masaki", "distance_from_prev_km": 0}],
                phone="+255700111222")

    def test_transport_requires_a_phone_number(self):
        frappe.set_user(CUSTOMER)
        with self.assertRaises(frappe.ValidationError):
            customer.place_transport_request(
                stops=[{"address": "A", "distance_from_prev_km": 0},
                       {"address": "B", "distance_from_prev_km": 5}],
                phone=None)

    # ------------------------------------------------------------ security
    def test_customer_cannot_open_the_operations_console(self):
        frappe.set_user(CUSTOMER)
        with self.assertRaises(frappe.PermissionError):
            operations.dashboard()

    def test_merchant_cannot_read_another_merchants_catalogue(self):
        frappe.set_user(MERCHANT_1)
        other = _merchant("Retail", user=MERCHANT_2)
        with self.assertRaises(frappe.PermissionError):
            merchant.catalog(merchant=other)

    def test_guest_cannot_place_an_order(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            customer.place_order(merchant=_merchant("Food"),
                                 items=[{"item": "X", "qty": 1}],
                                 delivery_address="Somewhere")

    def test_driver_cannot_touch_another_drivers_job(self):
        result, _ = self._place_food()
        ref = result["order"]

        frappe.set_user(MERCHANT_1)
        merchant.accept_order(ref, prep_minutes=15)
        frappe.set_user(OPS)
        operations.assign_driver(ref, _driver_for(DRIVER_1, "can_food"))

        frappe.set_user(DRIVER_2)
        with self.assertRaises(frappe.PermissionError):
            driver_api.job_detail(ref)

    def test_operations_dashboard_covers_all_services(self):
        self._place_food()
        frappe.set_user(OPS)
        d = operations.dashboard()
        self.assertIn("orders", d)
        self.assertIn("parcels", d)
        self.assertIn("transport", d)
        self.assertEqual(d["currency"],
                         frappe.get_cached_doc("Logistics Settings").currency)


if __name__ == "__main__":
    unittest.main()
