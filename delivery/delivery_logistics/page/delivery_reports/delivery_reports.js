// Desk page: Delivery Reports (admin "box 9").
// Renders end-of-day reports from delivery.api.operations.* INSIDE Desk:
// KPI tiles, period totals, merchant payables (items only) and driver payouts.
frappe.pages['delivery-reports'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Delivery Reports',
		single_column: true
	});

	var cur = 'TZS';
	function money(n) { return cur + ' ' + Number(n || 0).toLocaleString('en-US'); }

	if (!document.getElementById('fa-cdn-delivery')) {
		var fa = document.createElement('link');
		fa.id = 'fa-cdn-delivery';
		fa.rel = 'stylesheet';
		fa.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css';
		document.head.appendChild(fa);
	}

	frappe.dom.set_style(`
		.dlrep-wrap { max-width: 1080px; }
		.dlrep-kpi { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin: 4px 0 18px; }
		.dlrep-stat { display: flex; align-items: center; gap: 13px; background: #fff; border: 1px solid #E8E4F7;
			border-radius: 16px; padding: 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
		.dlrep-ic { width: 44px; height: 44px; border-radius: 13px; background: #F1ECFF; color: #5B2BE0;
			display: grid; place-items: center; font-size: 17px; flex: none; }
		.dlrep-stat b { display: block; font-size: 19px; font-weight: 800; color: #171717; line-height: 1.2; }
		.dlrep-stat span { font-size: 12px; color: #6B6B76; font-weight: 600; }
		.dlrep-card { background: #fff; border: 1px solid #E8E4F7; border-radius: 16px; padding: 18px;
			margin-bottom: 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
		.dlrep-card h3 { font-size: 14px; font-weight: 800; margin: 0 0 4px; color: #171717; }
		.dlrep-sub { font-size: 12px; color: #6B6B76; margin: 0 0 12px; }
		.dlrep-card table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.dlrep-card th { font-size: 10.5px; letter-spacing: .07em; color: #6B6B76; font-weight: 800;
			text-transform: uppercase; text-align: left; padding: 8px 10px; border-bottom: 2px solid #EEEBF7; }
		.dlrep-card td { padding: 10px; border-bottom: 1px solid #F3F1FA; color: #33323A; }
		.dlrep-card td.purple { color: #3F1BA8; font-weight: 800; }
		.dlrep-select { max-width: 300px; margin: 0 0 12px; }
		.dlrep-empty { color: #8A8A94; padding: 22px; text-align: center; font-size: 13px; }
	`);

	$(page.main).append(`
		<div class="dlrep-wrap">
			<div id="dlrep-kpi" class="dlrep-kpi"><div class="dlrep-card" style="grid-column:1/-1">Loading reports&hellip;</div></div>

			<div class="dlrep-card">
				<h3>Order totals by period</h3>
				<p class="dlrep-sub">Completed orders</p>
				<div id="dlrep-periods"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>

			<div class="dlrep-card">
				<h3>Payable to merchants</h3>
				<p class="dlrep-sub">Payable = item amounts only; service charges belong to the platform.</p>
				<select id="dlrep-merchant" class="dlrep-select form-control"><option value="">All merchants</option></select>
				<div id="dlrep-merchants"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>

			<div class="dlrep-card">
				<h3>Driver payouts</h3>
				<p class="dlrep-sub">70% of delivery fees on completed deliveries.</p>
				<select id="dlrep-driver" class="dlrep-select form-control"><option value="">All drivers</option></select>
				<div id="dlrep-drivers"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>
		</div>`);

	function stat(icon, val, label) {
		return '<div class="dlrep-stat"><span class="dlrep-ic"><i class="fa-solid ' + icon +
			'"></i></span><div><b>' + val + '</b><span>' + label + '</span></div></div>';
	}

	function renderReports(d) {
		cur = d.currency || cur;
		try {
			var payables = d.merchant_payables || [];
			var merchTotal = payables.reduce(function (s, m) { return s + m.payable; }, 0);
			$('#dlrep-kpi').html(
				stat('fa-store', money(merchTotal), 'Pay merchants (items only)') +
				stat('fa-sack-dollar', money(d.platform_revenue.total), 'Platform revenue') +
				stat('fa-building-columns', money(d.platform_revenue.delivery_office_share), 'Office 30% of fees') +
				stat('fa-percent', money(d.platform_revenue.service_fees), 'Service charges') +
				stat('fa-calendar-day', d.today.orders, 'Orders today') +
				stat('fa-calendar-week', d.week.orders, 'Orders this week'));
		} catch (e) {
			$('#dlrep-kpi').html('<div class="dlrep-card">' + frappe.utils.escape_html(e.message) + '</div>');
		}
		try {
			var per = [['Today', d.today], ['Last 7 days', d.week], ['This month', d.month], ['All time', d.all_time]];
			$('#dlrep-periods').html(
				'<table><thead><tr><th>Period</th><th>Orders</th><th>Items total</th><th>Service fees</th>' +
				'<th>Delivery fees</th><th>Grand total</th></tr></thead><tbody>' +
				per.map(function (p) {
					return '<tr><td><b>' + p[0] + '</b></td><td>' + p[1].orders + '</td>' +
						'<td>' + money(p[1].items_total) + '</td><td>' + money(p[1].service_fee_total) + '</td>' +
						'<td>' + money(p[1].delivery_fees) + '</td><td class="purple">' + money(p[1].grand_total) + '</td></tr>';
				}).join('') + '</tbody></table>');
		} catch (e) {
			$('#dlrep-periods').html('<div class="dlrep-empty">' + frappe.utils.escape_html(e.message) + '</div>');
		}
		try {
			var rows = d.merchant_payables || [];
			var $sel = $('#dlrep-merchant');
			$sel.html('<option value="">All merchants</option>' + rows.map(function (m) {
				return '<option value="' + m.merchant + '">' + frappe.utils.escape_html(m.merchant_name) + '</option>';
			}).join(''));
			$sel.off('change').on('change', renderMerchantRows);
			renderMerchantRows();
		} catch (e) {
			$('#dlrep-merchants').html('<div class="dlrep-empty">' + frappe.utils.escape_html(e.message) + '</div>');
		}
	}

	var MROWS = [];
	function renderMerchantRows() {
		var v = $('#dlrep-merchant').val();
		var show = MROWS.filter(function (m) { return !v || m.merchant === v; });
		$('#dlrep-merchants').html(show.length
			? '<table><thead><tr><th>Merchant</th><th>Completed</th><th>Order total</th><th>Service charges</th>' +
			  '<th>Payable (items)</th></tr></thead><tbody>' +
			  show.map(function (m) {
				  return '<tr><td><b>' + frappe.utils.escape_html(m.merchant_name) + '</b></td><td>' + m.orders + '</td>' +
					  '<td>' + money(m.order_total) + '</td><td>' + money(m.service_fee) + '</td>' +
					  '<td class="purple">' + money(m.payable) + '</td></tr>';
			  }).join('') +
			  '<tr><td><b>Total</b></td><td></td>' +
			  '<td><b>' + money(show.reduce(function (s, m) { return s + m.order_total; }, 0)) + '</b></td>' +
			  '<td><b>' + money(show.reduce(function (s, m) { return s + m.service_fee; }, 0)) + '</b></td>' +
			  '<td class="purple"><b>' + money(show.reduce(function (s, m) { return s + m.payable; }, 0)) + '</b></td></tr>' +
			  '</tbody></table>'
			: '<div class="dlrep-empty">No completed orders yet.</div>');
	}

	var DROWS = [];
	function renderDriverRows() {
		var v = $('#dlrep-driver').val();
		var show = DROWS.filter(function (d) { return !v || d.driver === v; });
		$('#dlrep-drivers').html(show.length
			? '<table><thead><tr><th>Driver</th><th>Phone</th><th>Completed</th><th>Fees collected</th>' +
			  '<th>Payable (' + (show[0].share_pct) + '%)</th></tr></thead><tbody>' +
			  show.map(function (d) {
				  return '<tr><td><b>' + frappe.utils.escape_html(d.driver_name) + '</b></td>' +
					  '<td>' + frappe.utils.escape_html(d.phone || '') + '</td><td>' + d.jobs + '</td>' +
					  '<td>' + money(d.fees_total) + '</td><td class="purple">' + money(d.payable) + '</td></tr>';
			  }).join('') + '</tbody></table>'
			: '<div class="dlrep-empty">No completed driver deliveries yet.</div>');
	}

	function load() {
		$('#dlrep-kpi').html('<div class="dlrep-card">Loading&hellip;</div>');
		frappe.call({
			method: 'delivery.api.operations.reports'
		}).then(function (r) {
			MROWS = (r.message && r.message.merchant_payables) || [];
			renderReports(r.message || {});
		});
		frappe.call({
			method: 'delivery.api.operations.driver_payouts'
		}).then(function (r) {
			DROWS = r.message || [];
			$('#dlrep-driver').html('<option value="">All drivers</option>' + DROWS.map(function (d) {
				return '<option value="' + d.driver + '">' + frappe.utils.escape_html(d.driver_name) + '</option>';
			}).join(''));
			$('#dlrep-driver').off('change').on('change', renderDriverRows);
			renderDriverRows();
		});
	}

	page.set_primary_action(__('Refresh'), load, 'fa fa-refresh');
	load();
};
