"""A5 benchmark — per-step evidence capture cost on the REAL landing page.

Measures the exact EvidenceTracker._record_step capture sequence on
landing/index.html (the 6533px page from the 09-15 audit) plus variants:

  A  current:  image-wait + full_page screenshot + Pillow WebP lossless (method=2)
  B  height-cap: clip top 2160px (3 viewports) + WebP lossless (method=2)
  C  viewport: 720p viewport shot + WebP lossless (method=2)
  D  current but PNG output (no re-encode)

Run:  python scripts/evidence_capture_benchmark.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io  # noqa: E402

from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from src.credential_redaction import masked_screenshot_page  # noqa: E402
from src.evidence_image import encode_evidence_image  # noqa: E402

HERE = Path(__file__).resolve().parent
PAGE_URL = f"file:///{(HERE.parent / 'landing' / 'index.html').as_posix()}"

IMAGE_WAIT_JS = """() => Promise.race([
    Promise.all(Array.from(document.images).map(
        img => img.complete ? Promise.resolve()
            : new Promise(res => {
                img.addEventListener('load', res, { once: true });
                img.addEventListener('error', res, { once: true });
            })
    )),
    new Promise(res => setTimeout(res, 4000)),
])"""


def timed(fn, *a, **k):
    t0 = time.perf_counter()
    out = fn(*a, **k)
    return time.perf_counter() - t0, out


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(PAGE_URL)
        page.wait_for_load_state("networkidle")
        height = page.evaluate("() => document.body.scrollHeight")
        print(f"landing page height: {height}px\n")

        rows: dict[str, list[float]] = {
            "image-wait": [],
            "full-shot": [],
            "cap-shot": [],
            "vp-shot": [],
            "enc-method2": [],
            "enc-method0": [],
            "enc-png": [],
        }
        sizes: dict[str, int] = {}

        for it in range(4):
            w, _ = timed(page.evaluate, IMAGE_WAIT_JS)
            rows["image-wait"].append(w)

            with masked_screenshot_page(page):
                ts, png_full = timed(page.screenshot, full_page=True)
                tc, png_cap = timed(
                    page.screenshot, clip={"x": 0, "y": 0, "width": 1280, "height": 2160}, full_page=True
                )
                tv, png_vp = timed(page.screenshot)
            rows["full-shot"].append(ts)
            rows["cap-shot"].append(tc)
            rows["vp-shot"].append(tv)

            te2, webp2 = timed(encode_evidence_image, png_full)

            def _enc_m0(data: bytes) -> bytes:
                buf = io.BytesIO()
                Image.open(io.BytesIO(data)).save(buf, format="WEBP", lossless=True, quality=100, method=0)
                return buf.getvalue()

            te0, _ = timed(_enc_m0, png_full)
            rows["enc-method2"].append(te2)
            rows["enc-method0"].append(te0)
            sizes["full_png_kb"] = len(png_full) // 1024
            sizes["cap_png_kb"] = len(png_cap) // 1024
            sizes["vp_png_kb"] = len(png_vp) // 1024
            sizes["full_webp_m2_kb"] = len(webp2) // 1024
            print(
                f"  iter {it + 1}: wait {w * 1000:5.0f}ms | full {ts * 1000:5.0f}ms | "
                f"cap {tc * 1000:5.0f}ms | vp {tv * 1000:5.0f}ms | "
                f"enc2 {te2 * 1000:5.0f}ms | enc0 {te0 * 1000:5.0f}ms"
            )

        m = lambda k: statistics.mean(rows[k]) * 1000  # noqa: E731
        print("\n--- mean over 4 iterations ---")
        print(f"  image-wait (4s cap)      {m('image-wait'):7.0f} ms")
        print(f"  full-page shot (1280x{height})  {m('full-shot'):7.0f} ms   ({sizes['full_png_kb']} KB png)")
        print(f"  height-capped 2160px shot       {m('cap-shot'):7.0f} ms   ({sizes['cap_png_kb']} KB png)")
        print(f"  viewport 720p shot              {m('vp-shot'):7.0f} ms   ({sizes['vp_png_kb']} KB png)")
        print(f"  webp lossless encode method=2   {m('enc-method2'):7.0f} ms   ({sizes['full_webp_m2_kb']} KB out)")
        print(f"  webp lossless encode method=0   {m('enc-method0'):7.0f} ms")
        print()
        print("  COMBINED per-step totals:")
        print(f"    A current (full+enc2)          {m('image-wait') + m('full-shot') + m('enc-method2'):7.0f} ms")
        print(
            f"    B height-capped (cap+enc2)     {m('image-wait') + m('cap-shot') + m('enc-method2') * 0.4:7.0f} ms  (enc scaled ~4x smaller img)"
        )
        print(
            f"    C viewport (vp+enc2)           {m('image-wait') + m('vp-shot') + m('enc-method2') * 0.15:7.0f} ms  (enc scaled ~7x smaller img)"
        )
        print(
            f"    D full PNG (no re-encode)      {m('image-wait') + m('full-shot'):7.0f} ms   ({sizes['full_png_kb']} KB out, no encode)"
        )
        browser.close()


if __name__ == "__main__":
    main()
