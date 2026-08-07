/*
 * Injectable consent/ad overlay for the banking mock (B-029 race).
 *
 * Every page includes this script. Overlays are injected ONLY on demand via
 * query parameter, so the mock serves a deterministic clean path by default:
 *
 *   ?overlay=consent   -> FreeCmp-style consent dialog covering the header
 *   ?overlay=ad        -> Google-vignette-style ad overlay (full viewport)
 *   ?overlay=consent+ad-> both (worst case)
 *   (none)             -> clean page, no overlays
 *
 * The injected markup mirrors the real-world selectors the scraper and the
 * EvidenceTracker dismissal logic target (`.fc-consent-root`,
 * `#google_vignette`, `#consent-root`), so the B-029 class — a click on a
 * nav link being swallowed by an overlay, with no navigation — is testable
 * deterministically instead of relying on random ad timing on live sites.
 *
 * Identical to the e-commerce mock's overlay.js — kept per-mock so each site
 * stays fully self-contained (a mock must never depend on a sibling dir).
 */
(function () {
  "use strict";

  function injectConsent() {
    var root = document.createElement("div");
    root.id = "consent-root";
    root.style.cssText =
      "position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;" +
      "background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;";

    var dialog = document.createElement("div");
    dialog.className = "fc-consent-root";
    dialog.style.cssText =
      "background:#fff;padding:24px;border-radius:8px;max-width:420px;" +
      "box-shadow:0 4px 24px rgba(0,0,0,0.35);font-family:sans-serif;text-align:center;";

    var title = document.createElement("h2");
    title.textContent = "We value your privacy";

    var body = document.createElement("p");
    body.textContent =
      "We use cookies to personalise content and analyse traffic. " +
      "Please make a choice below.";

    var accept = document.createElement("button");
    accept.id = "consent-accept";
    accept.className = "btn btn-success";
    accept.textContent = "Accept All";
    accept.addEventListener("click", function () {
      root.remove();
    });

    var reject = document.createElement("button");
    reject.id = "consent-reject";
    reject.className = "btn btn-default";
    reject.textContent = "Reject";
    reject.addEventListener("click", function () {
      root.remove();
    });

    dialog.appendChild(title);
    dialog.appendChild(body);
    dialog.appendChild(accept);
    dialog.appendChild(reject);
    root.appendChild(dialog);
    document.body.appendChild(root);
  }

  function injectAd() {
    // Mirror the Google vignette overlay the scraper knows how to remove.
    var ad = document.createElement("div");
    ad.id = "google_vignette";
    ad.style.cssText =
      "position:fixed;top:0;left:0;width:100%;height:100%;z-index:9998;" +
      "background:#f2f2f2;display:flex;align-items:center;justify-content:center;";
    var inner = document.createElement("div");
    inner.textContent = "ADVERTISEMENT";
    inner.style.cssText =
      "border:2px dashed #ccc;padding:48px;font-size:24px;color:#999;background:#fff;";
    ad.appendChild(inner);
    ad.addEventListener("click", function () {
      ad.remove();
    });
    document.body.appendChild(ad);
  }

  try {
    var params = new URLSearchParams(window.location.search);
    var overlay = params.get("overlay") || "";
    var apply = function () {
      if (overlay.indexOf("consent") !== -1) {
        injectConsent();
      }
      if (overlay.indexOf("ad") !== -1) {
        injectAd();
      }
    };
    if (document.body) {
      apply();
    } else {
      // Script runs from <head> — wait for the body before appending.
      document.addEventListener("DOMContentLoaded", apply);
    }
  } catch (e) {
    /* never break the page on overlay failure */
  }
})();
