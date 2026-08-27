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
      localStorage.setItem("dl_cart", JSON.stringify(this.cart));
      localStorage.setItem("dl_cart_merchant", this.cartMerchant || "");
      this.renderCartBadge();
    },
    addToCart: function (merchant, item, name, rate, qty) {
      if (this.cartMerchant && this.cartMerchant !== merchant) {
        if (!confirm("Your cart has items from another merchant. Clear it and start a new order?")) return;
        this.cart = [];
      }
      this.cartMerchant = merchant;
      var found = this.cart.filter(function (l) { return l.item === item; })[0];
      if (found) found.qty += Number(qty || 1);
      else this.cart.push({ item: item, item_name: name, rate: Number(rate), qty: Number(qty || 1) });
      this.saveCart();
      this.toast(name + " added to cart", "success");
    },
    cartTotal: function () {
      return this.cart.reduce(function (s, l) { return s + l.rate * l.qty; }, 0);
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
