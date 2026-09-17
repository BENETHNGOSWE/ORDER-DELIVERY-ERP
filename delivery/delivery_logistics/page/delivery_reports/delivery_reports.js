// Desk page: Delivery Reports (admin "box 9") — time-based financial reporting.
// Filter: Today / Yesterday / This Week / This Month / Custom range.
// EVERYTHING (KPI cards, merchant payables, driver payouts, transactions)
// is computed for the SELECTED period; the overview table keeps the fixed
// windows (today / last 7 days / this month / all time) for comparison.
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
		.dlrep-chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 2px 0 16px; }
		.dlrep-chip { border: 1.5px solid #E5E0F0; background: #fff; color: #33323A; border-radius: 999px;
			padding: 8px 16px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
		.dlrep-chip.active { background: #C6050C; border-color: #C6050C; color: #fff; }
		.dlrep-custom { display: none; gap: 8px; align-items: center; }
		.dlrep-custom.show { display: flex; flex-wrap: wrap; }
		.dlrep-custom input { border: 1.5px solid #E5E0F0; border-radius: 10px; padding: 7px 10px; font-size: 12.5px; }
		.dlrep-kpi { display: grid; gap: 14px; grid-template-columns: repeat(3, 1fr); margin: 4px 0 18px; }
		@media (max-width: 900px) { .dlrep-kpi { grid-template-columns: repeat(2, 1fr); } }
		@media (max-width: 560px) { .dlrep-kpi { grid-template-columns: 1fr; } }
		.dlrep-stat { display: flex; align-items: center; gap: 13px; background: #fff; border: 1px solid #F0DCDC;
			border-radius: 16px; padding: 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
		.dlrep-ic { width: 44px; height: 44px; border-radius: 13px; background: #FDECEC; color: #C6050C;
			display: grid; place-items: center; font-size: 17px; flex: none; }
		.dlrep-stat b { display: block; font-size: 19px; font-weight: 800; color: #171717; line-height: 1.2; }
		.dlrep-stat span { font-size: 12px; color: #6B6B76; font-weight: 600; }
		.dlrep-card { background: #fff; border: 1px solid #F0DCDC; border-radius: 16px; padding: 18px;
			margin-bottom: 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
		.dlrep-card h3 { font-size: 14px; font-weight: 800; margin: 0 0 4px; color: #171717; }
		.dlrep-sub { font-size: 12px; color: #6B6B76; margin: 0 0 12px; }
		.dlrep-card table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.dlrep-card th { font-size: 10.5px; letter-spacing: .07em; color: #6B6B76; font-weight: 800;
			text-transform: uppercase; text-align: left; padding: 8px 10px; border-bottom: 2px solid #F7E9E9; }
		.dlrep-card td { padding: 10px; border-bottom: 1px solid #FAF3F3; color: #33323A; }
		.dlrep-card td.red { color: #8F0409; font-weight: 800; }
		.dlrep-twrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
		.dlrep-twrap table { min-width: 560px; }
		.dlrep-select { max-width: 300px; margin: 0 0 12px; }
		.dlrep-empty { color: #8A8A94; padding: 22px; text-align: center; font-size: 13px; }
		.dlrep-period { display: inline-block; background: #FDECEC; color: #8F0409; font-weight: 800;
			font-size: 12px; border-radius: 999px; padding: 4px 12px; margin-bottom: 10px; }
	`);

	$(page.main).append(`
		<div class="dlrep-wrap">
			<div class="dlrep-chips" id="dlrep-chips">
				<button class="dlrep-chip active" data-p="today">Today</button>
				<button class="dlrep-chip" data-p="yesterday">Yesterday</button>
				<button class="dlrep-chip" data-p="week">This Week</button>
				<button class="dlrep-chip" data-p="month">This Month</button>
				<button class="dlrep-chip" data-p="custom">Custom</button>
				<span class="dlrep-custom" id="dlrep-custom">
					<input type="date" id="dlrep-from"><span style="font-size:12px;color:#6B6B76">to</span>
					<input type="date" id="dlrep-to">
					<button class="dlrep-chip active" id="dlrep-apply">Apply</button>
				</span>
			</div>
			<div id="dlrep-kpi" class="dlrep-kpi"><div class="dlrep-card">Loading reports&hellip;</div></div>

			<div class="dlrep-card">
				<h3>Payable to merchants</h3>
				<p class="dlrep-sub">Payable = item amounts only; service charges belong to the platform.</p>
				<select id="dlrep-merchant" class="dlrep-select form-control"><option value="">All merchants</option></select>
				<div id="dlrep-merchants"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>

			<div class="dlrep-card">
				<h3>Driver payouts</h3>
				<p class="dlrep-sub">Driver share of delivery fees on completed deliveries in the period.</p>
				<select id="dlrep-driver" class="dlrep-select form-control"><option value="">All drivers</option></select>
				<div id="dlrep-drivers"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>

			<div class="dlrep-card">
				<h3>Transactions in period</h3>
				<p class="dlrep-sub">Completed orders behind the numbers above (latest 50).</p>
				<div id="dlrep-tx"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>

			<div class="dlrep-card">
				<h3>Order totals by period (overview)</h3>
				<p class="dlrep-sub">Fixed comparison windows - independent of the filter above.</p>
				<div id="dlrep-periods"><div class="dlrep-empty">Loading&hellip;</div></div>
			</div>
		</div>`);

	var PERIOD = { key: 'today', from: null, to: null };

	function ymd(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
	function resolve(p) {
		var t = new Date(); t.setHours(0, 0, 0, 0);
		if (p === 'today') return [ymd(t), ymd(t)];
		if (p === 'yesterday') { var y = new Date(t); y.setDate(y.getDate() - 1); return [ymd(y), ymd(y)]; }
		if (p === 'week') { var m = new Date(t); var dow = (m.getDay() + 6) % 7; m.setDate(m.getDate() - dow); return [ymd(m), ymd(t)]; }
		if (p === 'month') { var f = new Date(t); f.setDate(1); return [ymd(f), ymd(t)]; }
		return [$('#dlrep-from').val(), $('#dlrep-to').val()];
	}
	function label() {
		return PERIOD.from === PERIOD.to ? PERIOD.from : PERIOD.from + '  →  ' + PERIOD.to;
	}

	function stat(icon, val, txt) {
		return '<div class="dlrep-stat"><span class="dlrep-ic"><i class="fa-solid ' + icon +
			'"></i></span><div><b>' + val + '</b><span>' + txt + '</span></div></div>';
	}

	function renderReports(d) {
		cur = d.currency || cur;
		$('#dlrep-kpi').html(
			'<div style="grid-column:1/-1"><span class="dlrep-period"><i class="fa-regular fa-calendar"></i> ' +
			frappe.utils.escape_html(label()) + '</span></div>' +
			stat('fa-store', money(d.platform_revenue.merchant_items), 'Pay merchants (items only)') +
			stat('fa-sack-dollar', money(d.platform_revenue.total), 'Platform revenue') +
			stat('fa-building-columns', money(d.platform_revenue.delivery_office_share), 'Office 30% of fees') +
			stat('fa-percent', money(d.platform_revenue.service_fees), 'Service charges') +
			stat('fa-motorcycle', money(DTOTAL), 'Driver payouts (' + (d.driver_share_pct || 70) + '% of fees)') +
			stat('fa-calendar-day', d.selected.orders, 'Completed orders in period'));

		var per = [['Today', d.today], ['Last 7 days', d.week], ['This month', d.month], ['All time', d.all_time]];
		$('#dlrep-periods').html(
			'<div class="dlrep-twrap"><table><thead><tr><th>Period</th><th>Orders</th><th>Items total</th><th>Service fees</th>' +
			'<th>Delivery fees</th><th>Grand total</th></tr></thead><tbody>' +
			per.map(function (p) {
				return '<tr><td><b>' + p[0] + '</b></td><td>' + p[1].orders + '</td>' +
					'<td>' + money(p[1].items_total) + '</td><td>' + money(p[1].service_fee_total) + '</td>' +
					'<td>' + money(p[1].delivery_fees) + '</td><td class="red">' + money(p[1].grand_total) + '</td></tr>';
			}).join('') + '</tbody></table></div>');

		var rows = d.merchant_payables || [];
		var $sel = $('#dlrep-merchant');
		$sel.html('<option value="">All merchants</option>' + rows.map(function (m) {
			return '<option value="' + m.merchant + '">' + frappe.utils.escape_html(m.merchant_name) + '</option>';
		}).join(''));
		$sel.off('change').on('change', renderMerchantRows);
		renderMerchantRows();

		var tx = d.recent_orders || [];
		$('#dlrep-tx').html(tx.length
			? '<div class="dlrep-twrap"><table><thead><tr><th>Order</th><th>Date</th><th>Merchant</th><th>Items</th>' +
			  '<th>Service</th><th>Delivery</th><th>Total</th><th>Payment</th></tr></thead><tbody>' +
			  tx.map(function (o) {
				  return '<tr><td><b>' + frappe.utils.escape_html(o.name) + '</b></td><td>' + frappe.utils.escape_html(o.date) + '</td>' +
					  '<td>' + frappe.utils.escape_html(o.merchant) + '</td><td>' + money(o.items_total) + '</td>' +
					  '<td>' + money(o.service_fee_total) + '</td><td>' + money(o.delivery_fee) + '</td>' +
					  '<td class="red">' + money(o.grand_total) + '</td><td>' + frappe.utils.escape_html(o.payment_status) + '</td></tr>';
			  }).join('') + '</tbody></table></div>'
			: '<div class="dlrep-empty">No completed orders in this period.</div>');
	}

	var MROWS = [];
	function renderMerchantRows() {
		var v = $('#dlrep-merchant').val();
		var show = MROWS.filter(function (m) { return !v || m.merchant === v; });
		$('#dlrep-merchants').html(show.length
			? '<div class="dlrep-twrap"><table><thead><tr><th>Merchant</th><th>Completed</th><th>Order total</th><th>Service charges</th>' +
			  '<th>Payable (items)</th></tr></thead><tbody>' +
			  show.map(function (m) {
				  return '<tr><td><b>' + frappe.utils.escape_html(m.merchant_name) + '</b></td><td>' + m.orders + '</td>' +
					  '<td>' + money(m.order_total) + '</td><td>' + money(m.service_fee) + '</td>' +
					  '<td class="red">' + money(m.payable) + '</td></tr>';
			  }).join('') +
			  '<tr><td><b>Total</b></td><td></td>' +
			  '<td><b>' + money(show.reduce(function (s, m) { return s + m.order_total; }, 0)) + '</b></td>' +
			  '<td><b>' + money(show.reduce(function (s, m) { return s + m.service_fee; }, 0)) + '</b></td>' +
			  '<td class="red"><b>' + money(show.reduce(function (s, m) { return s + m.payable; }, 0)) + '</b></td></tr>' +
			  '</tbody></table></div>'
			: '<div class="dlrep-empty">No completed orders in this period.</div>');
	}

	var DROWS = [], DTOTAL = 0;
	function renderDriverRows(dmeta) {
		var v = $('#dlrep-driver').val();
		var show = DROWS.filter(function (d) { return !v || d.driver === v; });
		$('#dlrep-drivers').html(show.length
			? '<div class="dlrep-twrap"><table><thead><tr><th>Driver</th><th>Phone</th><th>Completed</th><th>Fees collected</th>' +
			  '<th>Payable (' + (dmeta && dmeta.share_pct != null ? dmeta.share_pct : 70) + '%)</th></tr></thead><tbody>' +
			  show.map(function (d) {
				  return '<tr><td><b>' + frappe.utils.escape_html(d.driver_name) + '</b></td>' +
					  '<td>' + frappe.utils.escape_html(d.phone || '') + '</td><td>' + d.jobs + '</td>' +
					  '<td>' + money(d.fees_total) + '</td><td class="red">' + money(d.payable) + '</td></tr>';
			  }).join('') +
			  '<tr><td><b>Total</b></td><td></td><td></td><td><b>' +
			  money(show.reduce(function (s, d) { return s + d.fees_total; }, 0)) + '</b></td>' +
			  '<td class="red"><b>' + money(show.reduce(function (s, d) { return s + d.payable; }, 0)) + '</b></td></tr>' +
			  '</tbody></table></div>'
			: '<div class="dlrep-empty">No completed driver deliveries in this period.</div>');
	}

	function load() {
		var args = { from_date: PERIOD.from, to_date: PERIOD.to };
		$('#dlrep-kpi').html('<div class="dlrep-card">Loading&hellip;</div>');
		frappe.call({ method: 'delivery.api.operations.reports', args: args }).then(function (r) {
			var d = r.message || {};
			MROWS = d.merchant_payables || [];
			renderReports(d);
		});
		frappe.call({ method: 'delivery.api.operations.driver_payouts', args: args }).then(function (r) {
			var d = r.message || {};
			DROWS = d.drivers || [];
			DTOTAL = d.total_payable || 0;
			$('#dlrep-driver').html('<option value="">All drivers</option>' + DROWS.map(function (d) {
				return '<option value="' + d.driver + '">' + frappe.utils.escape_html(d.driver_name) + '</option>';
			}).join(''));
			$('#dlrep-driver').off('change').on('change', function () { renderDriverRows(d); });
			renderDriverRows(d);
			// refresh the driver KPI card with the real total
			var $el = $('.dlrep-stat').eq(4).find('b');
			if ($el.length) $el.text(money(DTOTAL));
		});
	}

	$('#dlrep-chips .dlrep-chip[data-p]').off('click').on('click', function () {
		$('#dlrep-chips .dlrep-chip').removeClass('active');
		$(this).addClass('active');
		var p = $(this).data('p');
		$('#dlrep-custom').toggleClass('show', p === 'custom');
		if (p === 'custom') return;
		var r = resolve(p);
		PERIOD = { key: p, from: r[0], to: r[1] };
		load();
	});
	$('#dlrep-apply').off('click').on('click', function () {
		var f = $('#dlrep-from').val(), t = $('#dlrep-to').val();
		if (!f || !t) { frappe.msgprint({ title: 'Select dates', indicator: 'orange', message: 'Choose both start and end dates.' }); return; }
		if (f > t) { frappe.msgprint({ title: 'Invalid range', indicator: 'orange', message: 'Start date must be before the end date.' }); return; }
		PERIOD = { key: 'custom', from: f, to: t };
		load();
	});

	page.set_primary_action(__('Refresh'), load, 'fa fa-refresh');
	var init = resolve('today');
	PERIOD = { key: 'today', from: init[0], to: init[1] };
	load();
};
