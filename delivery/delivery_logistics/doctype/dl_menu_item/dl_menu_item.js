// DL Menu Item form behaviour:
// - merchants: the Merchant field is read-only and pre-filled with their own
//   shop via delivery.api.merchant.whoami (a whitelisted, ownership-checked
//   call - client-side lookups on the Merchant doctype would fail because
//   merchants intentionally have no read permission on Merchant).
// - admins/operations: normal dropdown, free to pick any merchant.
frappe.ui.form.on("DL Menu Item", {
	setup(frm) { lock_merchant_field(frm); },
	onload(frm) { prefill_own_merchant(frm); },
	refresh(frm) { lock_merchant_field(frm); prefill_own_merchant(frm); },
});

function is_merchant_only() {
	const roles = frappe.user_roles || [];
	return roles.includes("Merchant User") &&
		!roles.includes("System Manager") &&
		!roles.includes("Delivery Operations");
}

function lock_merchant_field(frm) {
	if (is_merchant_only()) {
		frm.set_df_property("merchant", "read_only", 1);
		if (!frm._intro_set) {
			frm.set_intro(__("New items are automatically added to your shop."), false);
			frm._intro_set = 1;
		}
	}
}

function prefill_own_merchant(frm) {
	if (!is_merchant_only() || !frm.is_new() || frm.doc.merchant || frm._whoami_done) return;
	frm._whoami_done = 1;
	frappe.call({
		method: "delivery.api.merchant.whoami",
		callback(r) {
			if (!r || !r.message || !r.message.merchant) return;
			if (!frm.doc.merchant) frm.set_value("merchant", r.message.merchant);
		},
	});
}
