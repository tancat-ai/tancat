"""Regenerate the landing page's icon and social-card assets.

Run from the repo root (needs the ``landing/`` deps already installed):

    python scripts/maintenance/make_landing_assets.py

Writes into ``landing/``:

| File                   | Size            | Use                                  |
|------------------------|-----------------|--------------------------------------|
| ``favicon.ico``        | 16/32/48 px     | browser tab (multi-size ICO)         |
| ``icon-192.png``       | 192 px          | Android / PWA home screen            |
| ``icon-512.png``       | 512 px          | Android splash / PWA store           |
| ``apple-touch-icon.png``| 180 px         | iOS home screen (opaque, no alpha)   |
| ``og-card.png``        | 1200x630        | Open Graph / Twitter link preview    |

The icons come from ``landing/logo_transparent.png``, flattened onto the page's
``--midnight`` background (#070b10) so they look identical on light and dark
browser chrome.

The OG card is a **real capture of the page** rendered headless at 1200x630,
not a hand-made graphic -- so the preview can never advertise a headline the
page no longer shows. It needs the Tailwind CDN, so this step needs network.

Idempotent: same inputs + same Pillow/Chromium versions produce byte-similar
output. Nothing here ships to the product runtime.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

__all__ = ["main", "build_icons", "build_og_card"]

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDING = REPO_ROOT / "landing"
LOGO = LANDING / "logo_transparent.png"
INDEX = LANDING / "index.html"

# #070b10 -- keep in sync with `midnight` in landing/index.html.
MIDNIGHT: tuple[int, int, int, int] = (7, 11, 16, 255)
ICON_INSET = 0.06  # 6% breathing room around the logo circle
FAVICON_SIZES: tuple[int, ...] = (16, 32, 48)
PNG_ICONS: dict[str, int] = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "apple-touch-icon.png": 180,
}
OG_SIZE: tuple[int, int] = (1200, 630)


def _flattened_logo(size: int, logo: Image.Image) -> Image.Image:
    """Return a ``size`` x ``size`` opaque icon with the logo centred."""
    canvas = Image.new("RGBA", (size, size), MIDNIGHT)
    inset = round(size * ICON_INSET)
    inner = max(1, size - 2 * inset)
    scaled = logo.convert("RGBA").resize((inner, inner), Image.Resampling.LANCZOS)
    canvas.alpha_composite(scaled, (inset, inset))
    return canvas


def build_icons(logo_path: Path = LOGO, out_dir: Path = LANDING) -> list[Path]:
    """Write the favicon + PNG icon set derived from *logo_path*."""
    logo = Image.open(logo_path)
    written: list[Path] = []

    favicon_path = out_dir / "favicon.ico"
    _flattened_logo(256, logo).save(favicon_path, sizes=[(s, s) for s in FAVICON_SIZES])
    written.append(favicon_path)

    for name, size in PNG_ICONS.items():
        path = out_dir / name
        _flattened_logo(size, logo).convert("RGB").save(path, optimize=True)
        written.append(path)

    return written


def build_og_card(index_path: Path = INDEX, out_path: Path = LANDING / "og-card.png") -> Path:
    """Screenshot the page headless at 1200x630 into *out_path*."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": OG_SIZE[0], "height": OG_SIZE[1]}, device_scale_factor=1)
            page.goto(index_path.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(1200)  # webfonts settle after networkidle
            page.screenshot(path=str(out_path))
        finally:
            browser.close()
    return out_path


def main() -> int:
    """Regenerate every landing asset; print what was written."""
    for path in build_icons():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(f"wrote {build_og_card().relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
