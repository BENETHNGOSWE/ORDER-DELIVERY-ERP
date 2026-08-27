"""
Fee engine - SRS sections 3.1 to 3.3.

Expectations are derived from Logistics Settings rather than hardcoded, so the
suite stays correct when an operator retunes the platform fees.
"""
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from delivery.delivery_logistics import billing
from delivery.tests._helpers import _Fake


def _settings():
    return frappe.get_cached_doc("Logistics Settings")


class TestCurrency(FrappeTestCase):
    def test_platform_currency_is_honoured(self):
        self.assertEqual(billing._currency(), _settings().currency)

    def test_apply_currency_overrides_the_frappe_default(self):
        """
        A Currency *link* field takes its default from the global default
        currency (INR on a stock site), so it has to be assigned explicitly.
        """
        doc = _Fake(doctype="Parcel Request", currency="INR")
        billing.apply_currency(doc)
        self.assertEqual(doc.currency, _settings().currency)


class TestDeliveryFee(FrappeTestCase):
    def test_fee_is_base_plus_distance(self):
        s = _settings()
        r = billing.estimate_delivery_fee(zone=None, distance_km=5, items_total=0)
        expected = flt(s.base_delivery_fee) + flt(s.per_km_fee) * 5
        if flt(s.min_delivery_fee) and expected < flt(s.min_delivery_fee):
            expected = flt(s.min_delivery_fee)
        self.assertEqual(r["delivery_fee"], round(expected, 2))

    def test_minimum_fee_floor_applies(self):
        s = _settings()
        if not flt(s.min_delivery_fee):
            self.skipTest("no minimum fee configured")
        r = billing.estimate_delivery_fee(zone=None, distance_km=0, items_total=0)
        self.assertGreaterEqual(r["delivery_fee"], flt(s.min_delivery_fee))

    def test_free_delivery_above_threshold(self):
        s = _settings()
        if not flt(s.free_delivery_over):
            self.skipTest("no free-delivery threshold configured")
        r = billing.estimate_delivery_fee(
            zone=None, distance_km=5, items_total=flt(s.free_delivery_over) + 1)
        self.assertEqual(r["delivery_fee"], 0)
        self.assertTrue(r["free_delivery"])

    def test_quote_reports_its_currency(self):
        self.assertEqual(billing.estimate_delivery_fee()["currency"],
                         _settings().currency)

    def test_zero_distance_still_charges_the_base(self):
        r = billing.estimate_delivery_fee(zone=None, distance_km=0, items_total=0)
        self.assertGreater(r["delivery_fee"], 0)


class TestParcelBilling(FrappeTestCase):
    def _parcel(self, **kw):
        return _Fake(doctype="Parcel Request", weight_kg=1.0, length_cm=10,
                     width_cm=10, height_cm=10, distance_km=0, is_fragile=0,
                     billing_type=None, tariff_amount=0, **kw)

    def test_standard_weight_bills_instantly(self):
        needs_review, totals = billing.parcel_billing(self._parcel(weight_kg=1.5))
        self.assertFalse(needs_review)
        self.assertGreater(totals["tariff_amount"], 0)
        self.assertTrue(totals["weight_category"])

    def test_category_boundary_is_inclusive_at_the_bottom(self):
        band = billing.weight_category_for(0.5)
        self.assertIsNotNone(band)
        self.assertLessEqual(flt(band.min_weight_kg), 0.5)

    def test_heavy_parcel_needs_review(self):
        s = _settings()
        limit = flt(s.instant_weight_limit_kg) or 25
        needs_review, totals = billing.parcel_billing(
            self._parcel(weight_kg=limit + 60))
        self.assertTrue(needs_review)
        self.assertTrue(totals["is_heavy"])

    def test_oversized_parcel_needs_review(self):
        s = _settings()
        max_dim = flt(s.max_instant_dimension_cm) or 100
        needs_review, totals = billing.parcel_billing(
            self._parcel(weight_kg=2, length_cm=max_dim + 50))
        self.assertTrue(needs_review)
        self.assertTrue(totals["is_oversized"])

    def test_weight_charge_grows_with_weight(self):
        _, light = billing.parcel_billing(self._parcel(weight_kg=1.0))
        _, heavy = billing.parcel_billing(self._parcel(weight_kg=2.0))
        if light.get("weight_category") and heavy.get("weight_category"):
            self.assertGreater(heavy["tariff_amount"], light["tariff_amount"])

    def test_fragile_adds_a_surcharge(self):
        s = _settings()
        if not flt(s.fragile_surcharge_pct):
            self.skipTest("no fragile surcharge configured")
        _, plain = billing.parcel_billing(self._parcel(weight_kg=2))
        _, fragile = billing.parcel_billing(
            self._parcel(weight_kg=2, is_fragile=1))
        self.assertGreater(fragile["tariff_amount"], plain["tariff_amount"])

    def test_manual_tariff_is_never_overwritten(self):
        """Once staff agree a price the engine must leave it alone."""
        doc = self._parcel(weight_kg=1.5, billing_type="Negotiated",
                           tariff_amount=75000)
        needs_review, totals = billing.parcel_billing(doc)
        self.assertFalse(needs_review)
        self.assertEqual(totals["tariff_amount"], 75000)

    def test_set_manual_tariff_rejects_zero(self):
        with self.assertRaises(frappe.ValidationError):
            billing.set_manual_tariff(self._parcel(), 0)

    def test_set_manual_tariff_stores_the_agreed_price(self):
        doc = self._parcel(weight_kg=85)
        self.assertEqual(billing.set_manual_tariff(doc, 75000, "agreed"), 75000)
        self.assertEqual(doc.tariff_amount, 75000)
        self.assertEqual(doc.billing_type, "Negotiated")


class TestTransportFare(FrappeTestCase):
    def _req(self, stops, km):
        return _Fake(doctype="Transport Request",
                     total_distance_km=km,
                     route_stops=[{"idx": i + 1} for i in range(stops)])

    def test_reference_fare_formula(self):
        s = _settings()
        req = self._req(stops=3, km=34)
        expected = (flt(s.transport_base_fare)
                    + flt(s.transport_per_km) * 34
                    + flt(s.transport_per_stop) * 2)
        self.assertEqual(billing.transport_suggested_fare(req), round(expected, 2))

    def test_more_stops_cost_more(self):
        two = billing.transport_suggested_fare(self._req(stops=2, km=10))
        five = billing.transport_suggested_fare(self._req(stops=5, km=10))
        self.assertGreater(five, two)

    def test_more_distance_costs_more(self):
        short = billing.transport_suggested_fare(self._req(stops=2, km=5))
        long = billing.transport_suggested_fare(self._req(stops=2, km=50))
        self.assertGreater(long, short)

    def test_distance_is_summed_across_stops(self):
        req = _Fake(doctype="Transport Request", total_distance_km=None,
                    route_stops=[{"distance_from_prev_km": 4},
                                 {"distance_from_prev_km": 12.5},
                                 {"distance_from_prev_km": 6}])
        self.assertEqual(billing.transport_distance(req), 22.5)

    def test_quote_has_a_validity_window(self):
        self.assertGreaterEqual(billing.quote_validity_hours(), 1)


if __name__ == "__main__":
    unittest.main()
