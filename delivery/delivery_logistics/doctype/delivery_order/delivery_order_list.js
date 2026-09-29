// Desk list view for Delivery Order.
//
// The Workflow State COLUMN is coloured by the Workflow State master's
// `style` field (see delivery/patches/set_workflow_state_styles.py) -
// frappe consults that before this file, so keep the two in sync.
//
// This get_indicator colours the badge next to the document name (and
// the mobile cards) when the workflow's `override_status` is set, in
// which case the workflow branch in frappe.get_indicator is skipped.
frappe.listview_settings["Delivery Order"] = {
	add_fields: ["workflow_state"],

	get_indicator(doc) {
		var m = {
			REQUESTED: "gray",
			UNDER_REVIEW: "light-blue",
			PRICE_AGREED: "blue",
			PENDING: "orange",
			ACCEPTED: "light-blue",
			PREPARING: "blue",
			READY_FOR_DELIVERY: "red",
			DRIVER_ASSIGNED: "blue",
			PICKED_UP: "light-blue",
			COMPLETED: "green",
			CANCELLED: "gray",
		};
		var s = doc.workflow_state || "PENDING";
		return [__(s), m[s] || "gray", "workflow_state,=," + s];
	},
};
