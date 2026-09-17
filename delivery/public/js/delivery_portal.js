/* ==========================================================================
   Delivery & Logistics portal - shared client library
   No external dependencies. Works on the ERPNext website and, unchanged,
   inside a WebView / React Native shell for the future mobile app.
   ========================================================================== */
(function (window) {
  "use strict";

  var DELIVERY = {
    currency: "TZS",
    platform: "Delivery",
    cart: [],
    cartMerchant: null,

    /* ---- money ---- */
    fmt: function (n) {
      n = Number(n || 0);
      return this.currency + " " + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
    },

    /* ---- csrf ---- */
    /* Fetched once, over GET (which Frappe does not CSRF-protect), then reused
       for every POST. Guests get an empty token, which is correct. */
    _csrf: null,
    ensureCsrf: function () {
      if (window.csrf_token) return Promise.resolve(window.csrf_token);
      if (!this._csrf) {
        this._csrf = fetch("/api/method/delivery.portal.session_csrf", {
          credentials: "same-origin",
        }).then(function (r) { return r.json(); })
          .then(function (d) {
            window.csrf_token = (d && d.message) || "";
            return window.csrf_token;
          })
          .catch(function () { window.csrf_token = ""; return ""; });
      }
      return this._csrf;
    },

    /* ---- transport ---- */
    call: function (method, args) {
      return this.ensureCsrf().then(function (token) {
        return fetch("/api/method/" + method, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": token || "",
          },
          credentials: "same-origin",
          body: JSON.stringify(args || {}),
        });
      }).then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok || data.exc) {
            var msg = "Request failed";
            try {
              if (data._server_messages) {
                var parsed = JSON.parse(data._server_messages);
                msg = parsed.map(function (m) { return m.message; }).join(" ");
              } else if (data.exception) {
                msg = data.exception;
              }
            } catch (e) { /* fall through */ }
            throw new Error(msg.replace(/<[^>]*>/g, ""));
          }
          return data.message;
        });
      });
    },

    /* ---- feedback ---- */
    toast: function (msg, kind) {
      var el = document.getElementById("dl-toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "dl-toast";
        document.body.appendChild(el);
      }
      el.className = "dl-toast show " + (kind || "info");
      el.textContent = msg;
      clearTimeout(el._t);
      el._t = setTimeout(function () { el.className = "dl-toast"; }, 4200);
    },

    /* ---- cart (localStorage) ---- */
    loadCart: function () {
      try { this.cart = JSON.parse(localStorage.getItem("dl_cart") || "[]"); }
      catch (e) { this.cart = []; }
      this.cartMerchant = localStorage.getItem("dl_cart_merchant") || null;
      return this.cart;
    },
    saveCart: function () {
      if (!this.cart.length) this.cartMerchant = null;
      localStorage.setItem("dl_cart", JSON.stringify(this.cart));
      localStorage.setItem("dl_cart_merchant", this.cartMerchant || "");
      this.renderCartBadge();
    },
    /* ask what to do when the cart belongs to another merchant.
       onSwitch(true)  -> cart cleared, caller should add the new item
       onSwitch(false) -> keep the old cart (caller does nothing) */
    askMerchantSwitch: function (onSwitch) {
      if (document.getElementById("dl-sw-overlay")) { onSwitch(false); return; }
      var ov = document.createElement("div");
      ov.id = "dl-sw-overlay";
      ov.style.cssText = "position:fixed;inset:0;background:rgba(23,23,23,.5);z-index:9998;" +
        "display:flex;align-items:center;justify-content:center;padding:20px";
      ov.innerHTML =
        '<div style="background:#fff;border-radius:16px;max-width:400px;width:100%;padding:22px;' +
        'font-family:Inter,system-ui,sans-serif;box-shadow:0 20px 60px rgba(0,0,0,.3)">' +
        '<div style="width:46px;height:46px;border-radius:13px;background:#FDECEC;color:#C6050C;' +
        'display:grid;place-items:center;font-size:20px;margin-bottom:12px">' +
        '<i class="fa-solid fa-cart-shopping"></i></div>' +
        '<b style="font-size:16px;color:#171717">Your cart has items from another merchant.</b>' +
        '<p style="font-size:13.5px;color:#6B6B75;line-height:1.5;margin:8px 0 18px">' +
        "Submit that order first to proceed, or go back to your checkout.</p>" +
        '<div style="display:flex;gap:10px;flex-wrap:wrap">' +
        '<button id="dl-sw-submit" style="flex:1;min-width:150px;height:44px;border:0;border-radius:12px;' +
        'background:#C6050C;color:#fff;font-weight:700;font-size:14px;cursor:pointer">Submit order</button>' +
        '<button id="dl-sw-cancel" style="flex:1;min-width:150px;height:44px;border:1.5px solid #EAEAEF;' +
        'border-radius:12px;background:#fff;color:#171717;font-weight:700;font-size:14px;cursor:pointer">' +
        'Back to checkout</button></div></div>';
      document.body.appendChild(ov);
      ov.querySelector("#dl-sw-submit").addEventListener("click", function () {
        ov.remove(); onSwitch(true); location.href = "/delivery/cart";
      });
      ov.querySelector("#dl-sw-cancel").addEventListener("click", function () {
        ov.remove(); onSwitch(false); location.href = "/delivery/cart";
      });
    },
    addToCart: function (merchant, item, name, rate, qty, svc, opts) {
      if (this.cart.length && this.cartMerchant && this.cartMerchant !== merchant) {
        this.askMerchantSwitch(function (switched) {
          if (switched) {
            DELIVERY.cart = []; DELIVERY.cartMerchant = merchant;
            DELIVERY.addToCart(merchant, item, name, rate, qty, svc);
          }
        });
        return;
      }
      this.cartMerchant = merchant;
      svc = svc || {};
      var found = this.cart.filter(function (l) { return l.item === item; })[0];
      if (found) found.qty += Number(qty || 1);
      else this.cart.push({
        item: item, item_name: name, rate: Number(rate), qty: Number(qty || 1),
        svc_pct: Number(svc.pct || 0), svc_fee: Number(svc.fee || 0),
        eff_rate: Number(svc.eff || rate),
        flat_fee: Number(svc.flat || 0),
      });
      this.saveCart();
      this.toast(name + " added to cart", "success");
    },
    cartTotals: function () {
      var t = { base: 0, service: 0, flat: 0, grand: 0 };
      this.cart.forEach(function (l) {
        t.base += l.rate * l.qty;
        t.service += (l.svc_fee || 0) * l.qty;
        t.flat += (l.flat_fee || 0) * l.qty;
      });
      t.grand = t.base + t.service + t.flat;
      return t;
    },
    cartTotal: function () {
      return this.cartTotals().grand;
    },
    renderCartBadge: function () {
      var b = document.querySelector("[data-cart-count]");
      if (b) b.textContent = this.cart.reduce(function (s, l) { return s + l.qty; }, 0);
    },

    /* ---- state pill ---- */
    statePill: function (state) {
      var cls = {
        REQUESTED: "s-req", UNDER_REVIEW: "s-rev", PRICE_AGREED: "s-quo",
        PENDING: "s-pen", ACCEPTED: "s-acc", PREPARING: "s-pre",
        READY_FOR_DELIVERY: "s-rdy",
        DRIVER_ASSIGNED: "s-drv", PICKED_UP: "s-trn", COMPLETED: "s-don",
        CANCELLED: "s-can",
      }[state] || "s-req";
      return '<span class="pill ' + cls + '">' + state.replace(/_/g, " ") + "</span>";
    },

    esc: function (s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    },
  };

  window.DELIVERY = DELIVERY;
})(window);
