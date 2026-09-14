// DL Menu Item form behaviour:
// - merchants: the Merchant field is HIDDEN (no DocPerm on Merchant => any
//   link-title fetch would raise "No permission"); the shop name is shown
//   as plain intro text from delivery.api.merchant.whoami instead. The
//   server stamps the merchant on save, so the field value is never needed.
// - admins/operations: normal dropdown, free to pick any merchant.
frappe.ui.form.on("DL Menu Item", {
	setup(frm) { apply_merchant_view(frm); },
	refresh(frm) { apply_merchant_view(frm); whoami_shop_name(frm); },
	onload(frm) { whoami_shop_name(frm); },
});

function is_merchant_only() {
	const roles = frappe.user_roles || [];
	return roles.includes("Merchant User") &&
		!roles.includes("System Manager") &&
		!roles.includes("Delivery Operations");
}

function apply_merchant_view(frm) {
	if (is_merchant_only()) {
		frm.set_df_property("merchant", "hidden", 1);
		if (!frm._intro_set) {
			frm.set_intro(__("New items are automatically added to your shop."), false);
			frm._intro_set = 1;
		}
	}
}

function whoami_shop_name(frm) {
	if (!is_merchant_only() || frm._whoami_done) return;
	frm._whoami_done = 1;
	frappe.call({
		method: "delivery.api.merchant.whoami",
		callback(r) {
			if (!r || !r.message || !r.message.merchant_name) return;
			// replace the intro with the concrete shop name (plain text,
			// no link fetch, no permission check involved)
			if (frm._intro_set) {
				frm.set_intro(__("New items are automatically added to your shop: {0}",
					[r.message.merchant_name]), false);
			}
		},
	});
}
