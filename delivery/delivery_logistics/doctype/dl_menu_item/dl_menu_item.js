// DL Menu Item form behaviour:
// - merchants: the Merchant field is HIDDEN (no DocPerm on Merchant => any
//   link-title fetch would raise "No permission"); the shop name is shown
//   as plain intro text from delivery.api.merchant.whoami instead. The
//   server stamps the merchant on save, so the field value is never needed.
// - admins/operations: normal dropdown, free to pick any merchant.
// - live preview: while editing, the "Service Charge %" field description
//   shows the price the customer will pay (base + service %).
frappe.ui.form.on("DL Menu Item", {
	setup(frm) { apply_merchant_view(frm); },
	refresh(frm) { apply_merchant_view(frm); whoami_shop_name(frm); svc_price_preview(frm); },
	onload(frm) { whoami_shop_name(frm); },
	standard_rate(frm) { svc_price_preview(frm); },
	apply_service_charge(frm) { svc_price_preview(frm); },
	service_charge_pct(frm) { svc_price_preview(frm); },
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

// ---- live "customer sees" preview on the Service Charge section ----
function money(n) {
	return "TZS " + Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function svc_price_preview(frm) {
	const base = flt(frm.doc.standard_rate);
	const on = cint(frm.doc.apply_service_charge);
	const pct = flt(frm.doc.service_charge_pct);
	const flat = flt(frm.doc.service_fee);
	let txt = __("Added on top of the item price; shown to the customer as part of the total.");
	if (on && pct > 0 && base > 0) {
		const svc = Math.round(base * pct) / 100;
		txt = __("Customer sees: {0}  ({1} + {2} service at {3}%)",
			[money(base + svc), money(base), money(svc), pct]);
	} else if (on && pct > 0) {
		txt = __("Enter the item price to preview the customer total.");
	} else if (on) {
		txt = __("Enter the service percentage (e.g. 3 for 3%).");
	}
	if (flat > 0) {
		txt += " " + __("Plus a flat {0} service fee per item at checkout.", [money(flat)]);
	}
	frm.set_df_property("service_charge_pct", "description", txt);
}
