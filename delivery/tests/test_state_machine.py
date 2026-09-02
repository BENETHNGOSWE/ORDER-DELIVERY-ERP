"""
Master state matrix - SRS v2.2.0 section 5.

These run against a lightweight document stub, so the whole matrix is covered
without a database round trip per assertion.
"""
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from delivery.delivery_logistics import state_machine as sm
from delivery.tests._helpers import _Fake


class TestStateMatrix(FrappeTestCase):
    def test_all_nine_states_present(self):
        self.assertEqual(sm.STATES, [
            "REQUESTED", "UNDER_REVIEW", "PRICE_AGREED", "PENDING", "ACCEPTED",
            "PREPARING", "DRIVER_ASSIGNED", "PICKED_UP", "COMPLETED", "CANCELLED"])

    def test_completed_is_terminal(self):
        self.assertEqual(sm.next_states("COMPLETED"), [])

    def test_cancelled_is_terminal(self):
        self.assertEqual(sm.next_states("CANCELLED"), [])

    def test_cancel_reachable_from_every_non_terminal_state(self):
        for state in sm.STATES:
            if state in sm.TERMINAL:
                continue
            self.assertIn("CANCELLED", sm.ALLOWED[state], state)

    def test_requested_can_open_review_or_pricing(self):
        self.assertIn("UNDER_REVIEW", sm.ALLOWED["REQUESTED"])
        self.assertIn("PRICE_AGREED", sm.ALLOWED["REQUESTED"])

    def test_under_review_must_be_priced_before_proceeding(self):
        self.assertIn("PRICE_AGREED", sm.ALLOWED["UNDER_REVIEW"])
        self.assertNotIn("ACCEPTED", sm.ALLOWED["UNDER_REVIEW"])

    def test_food_retail_starts_pending_not_requested(self):
        """SRS marks REQUESTED/UNDER_REVIEW/PRICE_AGREED as n/a for food."""
        self.assertEqual(sm.SERVICE_ENTRY["Food"], "PENDING")
        self.assertEqual(sm.SERVICE_ENTRY["Retail"], "PENDING")
        self.assertIn("REQUESTED", sm.SERVICE_NOT_APPLICABLE["Food"])

    def test_parcel_starts_requested(self):
        self.assertEqual(sm.SERVICE_ENTRY["Parcel"], "REQUESTED")

    def test_transport_starts_under_review(self):
        self.assertEqual(sm.SERVICE_ENTRY["Transport"], "UNDER_REVIEW")

    def test_srs_labels_for_each_service(self):
        self.assertEqual(sm.SERVICE_LABELS["Food"]["PREPARING"], "Kitchen/Packing")
        self.assertEqual(sm.SERVICE_LABELS["Parcel"]["UNDER_REVIEW"], "Manual Quote")
        self.assertEqual(sm.SERVICE_LABELS["Transport"]["PICKED_UP"], "Route Active")
        self.assertEqual(sm.SERVICE_LABELS["Transport"]["COMPLETED"], "Trip Completed")

    def test_applicable_states_skip_not_applicable(self):
        doc = _Fake(order_type="Food")
        states = sm.applicable_states(doc)
        self.assertNotIn("UNDER_REVIEW", states)
        self.assertIn("PENDING", states)

    def test_full_food_lifecycle_is_legal(self):
        doc = _Fake(order_type="Food")
        for state in ["PENDING", "ACCEPTED", "PREPARING", "DRIVER_ASSIGNED",
                      "PICKED_UP", "COMPLETED"]:
            sm.set_state(doc, state)
        self.assertEqual(doc.workflow_state, "COMPLETED")

    def test_full_transport_lifecycle_is_legal(self):
        doc = _Fake(doctype="Transport Request")
        for state in ["UNDER_REVIEW", "PRICE_AGREED", "ACCEPTED", "PREPARING",
                      "DRIVER_ASSIGNED", "PICKED_UP", "COMPLETED"]:
            sm.set_state(doc, state)
        self.assertEqual(doc.workflow_state, "COMPLETED")

    def test_illegal_transition_is_rejected(self):
        doc = _Fake(order_type="Food")
        sm.set_state(doc, "PENDING")
        with self.assertRaises(frappe.ValidationError):
            sm.set_state(doc, "COMPLETED")   # cannot skip to the end

    def test_backward_transition_is_rejected(self):
        doc = _Fake(order_type="Food")
        sm.set_state(doc, "PENDING")
        sm.set_state(doc, "ACCEPTED")
        with self.assertRaises(frappe.ValidationError):
            sm.set_state(doc, "PENDING")

    def test_audit_trail_records_every_move(self):
        doc = _Fake(order_type="Food")
        for state in ["PENDING", "ACCEPTED", "PREPARING"]:
            sm.set_state(doc, state, note="step")
        trail = sm.timeline(doc)
        self.assertEqual([t["state"] for t in trail],
                         ["PENDING", "ACCEPTED", "PREPARING"])
        self.assertTrue(all(t["timestamp"] for t in trail))

    def test_completion_stamps_the_time(self):
        doc = _Fake(order_type="Food", workflow_state="PICKED_UP",
                    otp_code="1234", payment_method="Cash On Delivery")
        sm.set_state(doc, "COMPLETED")
        self.assertTrue(doc.completed_at)

    def test_cod_settles_on_completion(self):
        doc = _Fake(order_type="Food", workflow_state="PICKED_UP",
                    otp_code="1234", payment_method="Cash On Delivery",
                    payment_status="Pending")
        sm.set_state(doc, "COMPLETED")
        self.assertEqual(doc.payment_status, "Paid")

    def test_prepaid_order_stays_paid_not_double_settled(self):
        doc = _Fake(order_type="Food", workflow_state="PICKED_UP",
                    otp_code="1234", payment_method="M-Pesa",
                    payment_status="Paid")
        sm.set_state(doc, "COMPLETED")
        self.assertEqual(doc.payment_status, "Paid")

    def test_pickup_stamps_the_time(self):
        doc = _Fake(order_type="Food", workflow_state="DRIVER_ASSIGNED")
        sm.set_state(doc, "PICKED_UP")
        self.assertTrue(doc.picked_up_at)

    def test_driver_assignment_issues_an_otp(self):
        doc = _Fake(order_type="Food", workflow_state="PREPARING",
                    assigned_driver="DRV-001")
        sm.set_state(doc, "DRIVER_ASSIGNED")
        self.assertRegex(str(doc.otp_code), r"^\d{4}$")

    def test_unknown_state_is_rejected(self):
        doc = _Fake(order_type="Food")
        with self.assertRaises(frappe.ValidationError):
            sm.set_state(doc, "TELEPORTED")


if __name__ == "__main__":
    unittest.main()
