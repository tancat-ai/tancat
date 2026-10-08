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
| ``preview_desktop_1280.png`` | 1280 wide, full page | README / release preview        |
| ``preview_mobile_390.png``   | 390 wide, full page  | README / release preview            |
| ``tancat-pro-install-and-licence.pdf`` | A4   | Lemon Squeezy product deliverable    |

The icons come from ``landing/logo_transparent.png``, flattened onto the page's
``--midnight`` background (#070b10) so they look identical on light and dark
browser chrome.

The OG card, both preview screenshots and the install/licence PDF are **real
renders of their source pages**, not hand-made graphics -- so they can never
advertise wording the page or the document no longer shows. The landing renders
need the Tailwind CDN, so this step needs network.

Run this after ANY landing or install-document copy change: a stale share image
or PDF is the difference between a page that is fixed and one that still says
the old thing.

Every run also rewrites ``landing/asset-sources.json``, the fingerprint that
``scripts/maintenance/landing_assets_guard.py`` checks in CI and in a pre-commit
hook. The guard catches a source edit that was committed without this rebuild;
it does not re-render, because browser captures and the PDF are not
byte-reproducible across machines. Commit the manifest with the assets.

Idempotent: same inputs + same Pillow/Chromium versions produce byte-similar
output (the icons are byte-identical; the browser captures are not, so the
guard uses a source fingerprint rather than a render diff). Nothing here ships
to the product runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page, Playwright

__all__ = [
    "main",
    "build_icons",
    "build_og_card",
    "build_previews",
    "build_install_pdf",
    "ASSET_SOURCES",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDING = REPO_ROOT / "landing"
LOGO = LANDING / "logo_transparent.png"
INDEX = LANDING / "index.html"
#: The one-page Pro install/licence document Lemon Squeezy ships. Its source is
#: an HTML file so the PDF can be rebuilt instead of hand-edited.
INSTALL_HTML = REPO_ROOT / "docs" / "implementation" / "tancat-pro-install-and-licence.html"
INSTALL_PDF = LANDING / "tancat-pro-install-and-licence.pdf"

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

#: Full-page preview screenshots: file name -> (viewport width, viewport height).
#: ``full_page`` makes the written image as tall as the rendered page, so the
#: height here only sets the layout width used while rendering.
PREVIEW_VIEWPORTS: dict[str, tuple[int, int]] = {
    "preview_desktop_1280.png": (1280, 900),
    "preview_mobile_390.png": (390, 844),
}

#: Generated asset -> the repo-relative sources it is rendered from. This is the
#: contract the freshness guard checks: edit a source here and the guard fails
#: until the generator has re-rendered and rewritten the manifest. The browser
#: captures also depend on the webfonts fetched from Google Fonts, which cannot
#: be hashed; the fingerprint covers the files that are committed.
ASSET_SOURCES: dict[str, tuple[str, ...]] = {
    "favicon.ico": ("landing/logo_transparent.png",),
    "icon-192.png": ("landing/logo_transparent.png",),
    "icon-512.png": ("landing/logo_transparent.png",),
    "apple-touch-icon.png": ("landing/logo_transparent.png",),
    "og-card.png": ("landing/index.html", "landing/tailwind.css"),
    "preview_desktop_1280.png": ("landing/index.html", "landing/tailwind.css"),
    "preview_mobile_390.png": ("landing/index.html", "landing/tailwind.css"),
    "tancat-pro-install-and-licence.pdf": ("docs/implementation/tancat-pro-install-and-licence.html",),
}


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


def _open_page(index_path: Path, width: int, height: int) -> tuple[Playwright, tuple[Browser, Page]]:
    """Return (playwright, (browser, page)) with the landing page loaded."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    page.goto(index_path.as_uri(), wait_until="networkidle")
    page.wait_for_timeout(1200)  # webfonts settle after networkidle
    return playwright, (browser, page)


def build_og_card(index_path: Path = INDEX, out_path: Path = LANDING / "og-card.png") -> Path:
    """Screenshot the page headless at 1200x630 into *out_path*."""
    playwright, (browser, page) = _open_page(index_path, OG_SIZE[0], OG_SIZE[1])
    try:
        page.screenshot(path=str(out_path))
    finally:
        browser.close()
        playwright.stop()
    return out_path


def build_previews(index_path: Path = INDEX, out_dir: Path = LANDING) -> list[Path]:
    """Write the full-page desktop and mobile preview screenshots.

    Captures of the same page, so they cannot drift from the live copy the way a
    hand-made graphic does.
    """
    written: list[Path] = []
    for name, (width, height) in PREVIEW_VIEWPORTS.items():
        playwright, (browser, page) = _open_page(index_path, width, height)
        try:
            path = out_dir / name
            page.screenshot(path=str(path), full_page=True)
            written.append(path)
        finally:
            browser.close()
            playwright.stop()
    return written


def build_install_pdf(source_html: Path = INSTALL_HTML, out_path: Path = INSTALL_PDF) -> Path:
    """Render the install/licence document HTML to the deliverable PDF.

    The PDF is the one-page document Lemon Squeezy ships on the product. Its
    source is HTML so a copy correction can be rebuilt into the PDF instead of
    hand-editing it and leaving the two out of step.
    """
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    try:
        page = browser.new_page()
        page.goto(source_html.as_uri(), wait_until="load")
        page.pdf(path=str(out_path), format="A4", print_background=True)
    finally:
        browser.close()
        playwright.stop()
    return out_path


def main() -> int:
    """Regenerate every landing asset; print what was written."""
    for path in build_icons():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(f"wrote {build_og_card().relative_to(REPO_ROOT)}")
    for path in build_previews():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(f"wrote {build_install_pdf().relative_to(REPO_ROOT)}")

    # Imported here so the generator can be read/loaded without the guard on
    # sys.path, and so the manifest format lives in exactly one place.
    from landing_assets_guard import write_manifest

    manifest = write_manifest(ASSET_SOURCES, generator_path=Path(__file__))
    print(f"wrote {manifest.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
