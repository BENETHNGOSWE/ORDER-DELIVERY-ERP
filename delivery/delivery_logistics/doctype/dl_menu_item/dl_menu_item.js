// DL Menu Item form behaviour:
// merchants see the Merchant field read-only (their own merchant is stamped
// server-side); admins/operations keep the normal dropdown selection.
frappe.ui.form.on("DL Menu Item", {
	setup(frm) { apply_merchant_lock(frm); },
	refresh(frm) { apply_merchant_lock(frm); },
});

function apply_merchant_lock(frm) {
	const roles = frappe.user_roles || [];
	const isMerchant = roles.includes("Merchant User");
	const isStaff = roles.includes("System Manager") || roles.includes("Delivery Operations");
	if (isMerchant && !isStaff) {
		frm.set_df_property("merchant", "read_only", 1);
		frm.set_intro(__("New items are automatically added to your shop."), false);
	}
}
