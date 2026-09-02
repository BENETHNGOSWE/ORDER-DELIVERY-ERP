"""Dispatch Trip - groups the stops a driver runs in one outing."""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class DispatchTrip(Document):
    def validate(self):
        self.stop_count = len(self.get("trip_stops") or [])
        if self.get("driver") and not self.get("driver_name_f"):
            self.driver_name_f = frappe.db.get_value(
                "Delivery Driver", self.driver, "driver_name")

    def start(self):
        self.status = "Started"
        self.started_at = now_datetime()
        self.save(ignore_permissions=True)
        return self

    def complete(self):
        for stop in (self.get("trip_stops") or []):
            stop.status = "Completed"
        self.status = "Completed"
        self.completed_at = now_datetime()
        self.save(ignore_permissions=True)
        return self
