/*
 * Offline product images for the e-commerce mock.
 *
 * Fills every <img data-label="..."> with an inline SVG data URI — fully
 * deterministic, zero external network requests (no placeholder CDNs).
 */
(function () {
  "use strict";
  function fill() {
    document.querySelectorAll("img[data-label]").forEach(function (img) {
      var label = img.getAttribute("data-label") || "Product";
      var svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140">' +
        '<rect width="200" height="140" fill="#eef2f7"/>' +
        '<text x="100" y="72" font-family="Arial" font-size="16" fill="#7f8c8d" ' +
        'text-anchor="middle">' +
        label +
        "</text></svg>";
      img.src = "data:image/svg+xml," + encodeURIComponent(svg);
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fill);
  } else {
    fill();
  }
})();
