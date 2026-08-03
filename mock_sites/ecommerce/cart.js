/*
 * Cart state for the e-commerce mock (localStorage-backed, deterministic).
 *
 * Mirrors the automationexercise interaction surface the pipeline already
 * knows: `#cartModal` confirmation modal, `.btn-success.close-modal` continue
 * button, `#cart_items` table on the cart page.
 */
(function () {
  "use strict";

  var CART_KEY = "mock_ecommerce_cart";

  function getCart() {
    try {
      return JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
  }

  function addToCart(productId, name, price, quantity) {
    var cart = getCart();
    var qty = quantity || 1;
    var existing = null;
    for (var i = 0; i < cart.length; i++) {
      if (cart[i].id === productId) {
        existing = cart[i];
        break;
      }
    }
    if (existing) {
      existing.qty += qty;
    } else {
      cart.push({ id: productId, name: name, price: price, qty: qty });
    }
    saveCart(cart);
  }

  window.MockCart = {
    getCart: getCart,
    addToCart: addToCart,
    clear: function () {
      saveCart([]);
    },
  };

  // Attach to any [data-add-to-cart] button: <button data-add-to-cart
  // data-product-id="1" data-name="Blue Top" data-price="500">Add to cart</button>
  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-add-to-cart]");
    if (!btn) {
      return;
    }
    event.preventDefault();
    var quantity = 1;
    var qtyInput = document.getElementById("quantity");
    if (qtyInput && qtyInput.value) {
      quantity = parseInt(qtyInput.value, 10) || 1;
    }
    addToCart(
      btn.getAttribute("data-product-id"),
      btn.getAttribute("data-name"),
      parseInt(btn.getAttribute("data-price"), 10) || 0,
      quantity
    );

    // Show the confirmation modal (#cartModal) — same classes as the live
    // site so dismissal/scoping logic operates on real selectors.
    var modal = document.getElementById("cartModal");
    if (modal) {
      var nameEl = modal.querySelector(".modal-title");
      if (nameEl) {
        nameEl.textContent = "Added!";
      }
      var bodyEl = modal.querySelector("p.text-center");
      if (bodyEl) {
        bodyEl.textContent = "Your product has been added to cart.";
      }
      modal.style.display = "block";
    }
  });

  // Dismiss modal handlers (Continue Shopping / View Cart)
  document.addEventListener("click", function (event) {
    var close = event.target.closest(".close-modal, #cartModal .btn-default");
    if (!close) {
      return;
    }
    var modal = document.getElementById("cartModal");
    if (modal) {
      modal.style.display = "none";
    }
    // "View Cart" navigates away via its href; preventDefault only for close.
    if (close.classList.contains("close-modal")) {
      event.preventDefault();
    }
  });

  // Render the cart table on cart.html
  function renderCartTable() {
    var tbody = document.querySelector("#cart_items tbody");
    if (!tbody) {
      return;
    }
    var cart = getCart();
    var emptyMsg = document.getElementById("empty_cart");
    if (cart.length === 0) {
      if (emptyMsg) {
        emptyMsg.style.display = "block";
      }
      return;
    }
    if (emptyMsg) {
      emptyMsg.style.display = "none";
    }
    tbody.innerHTML = "";
    cart.forEach(function (item) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        '<td class="cart_description"><h4>' +
        item.name +
        "</h4></td>" +
        '<td class="cart_price"><p>Rs. ' +
        item.price +
        "</p></td>" +
        '<td class="cart_quantity"><p>' +
        item.qty +
        "</p></td>" +
        '<td class="cart_total"><p>Rs. ' +
        item.price * item.qty +
        "</p></td>";
      tbody.appendChild(tr);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderCartTable);
  } else {
    renderCartTable();
  }
})();
