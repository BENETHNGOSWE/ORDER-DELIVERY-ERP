// DL Menu Item form behaviour:
// - merchants: the Merchant field is read-only and pre-filled with their own
//   shop (server-side validate() stamps it anyway - this is pure UX so they
//   see the name); attachments on new items stay permitted.
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
	if (!is_merchant_only() || !frm.is_new() || frm.doc.merchant) return;
	frappe.db.get_value("Merchant", { portal_user: frappe.session.user }, "name")
		.then((r) => {
			const name = r && r.message && r.message.name;
			if (name && !frm.doc.merchant) frm.set_value("merchant", name);
		});
}
