"""Website health: the landing/docs gaps closed for the t-0577 audit.

Offline and fast - it reads the committed HTML, sitemap, Markdown and MkDocs
config. It pins each fix so a later edit cannot silently drop a 404 page, an
Open Graph tag on a sub-page, the docs favicon, a per-page description,
the docs entry in the root sitemap, or the mobile nav.

The live build is covered separately: CI job ``docs-build`` runs
``mkdocs build --strict`` and ``pages-deploy`` stages the site.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANDING = PROJECT_ROOT / "landing"
DOCS = PROJECT_ROOT / "docs" / "user"
MKDOCS = PROJECT_ROOT / "mkdocs.yml"

#: Sub-pages the audit found without Open Graph tags (index.html always had them).
OG_SUBPAGES = ("install.html", "privacy.html", "terms.html", "dpa.html")
OG_PROPERTIES = (
    "og:type",
    "og:site_name",
    "og:locale",
    "og:url",
    "og:title",
    "og:description",
    "og:image",
    "og:image:width",
    "og:image:height",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _docs_pages() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def _front_matter(text: str) -> str | None:
    """Return the YAML front-matter block, or None when the page has none."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


# --- 404 pages ---------------------------------------------------------------


def test_landing_404_exists_and_is_noindex() -> None:
    html = _read(LANDING / "404.html")
    assert 'name="robots" content="noindex"' in html
    assert "This page does not exist." in html


def test_landing_404_uses_root_absolute_internal_links() -> None:
    """GitHub Pages serves this one file for a missing URL at any depth.

    A request for /docs/typo returns the root 404.html with the URL unchanged,
    so relative links would resolve under /docs/ and break. Every internal link
    must be root-absolute.
    """
    html = _read(LANDING / "404.html")
    refs = re.findall(r'(?:href|src)="([^"]+)"', html)
    assert refs
    for ref in refs:
        if ref.startswith(("https://", "mailto:", "#")):
            continue
        assert ref.startswith("/"), f"404 page uses a depth-relative link: {ref}"
    assert 'href="/"' in html
    assert 'href="/docs/"' in html


def test_docs_404_override_exists_and_is_configured() -> None:
    override = PROJECT_ROOT / "overrides" / "404.html"
    assert override.is_file()
    html = _read(override)
    assert 'extends "main.html"' in html
    assert "Page not found" in html
    config = yaml.safe_load(_read(MKDOCS))
    assert config["theme"]["custom_dir"] == "overrides"


# --- Open Graph on the sub-pages ---------------------------------------------


def test_subpages_have_open_graph_and_twitter_tags() -> None:
    for name in OG_SUBPAGES:
        html = _read(LANDING / name)
        for prop in OG_PROPERTIES:
            assert f'property="{prop}"' in html, f"{name} missing {prop}"
        assert 'name="twitter:card" content="summary_large_image"' in html, name
        assert 'name="twitter:image"' in html, name


def test_open_graph_card_is_a_real_asset() -> None:
    card = LANDING / "og-card.png"
    assert card.is_file() and card.stat().st_size > 0


# --- docs favicon ------------------------------------------------------------


def test_mkdocs_favicon_configured_and_file_present() -> None:
    config = yaml.safe_load(_read(MKDOCS))
    favicon = config["theme"]["favicon"]
    assert favicon
    assert (DOCS / favicon).is_file()


def test_docs_favicon_matches_the_landing_favicon() -> None:
    """One icon, two homes: build_icons() writes both, so they must not drift."""
    assert (DOCS / "assets" / "favicon.ico").read_bytes() == (LANDING / "favicon.ico").read_bytes()


# --- per-page meta descriptions ----------------------------------------------


def test_every_docs_page_has_a_front_matter_description() -> None:
    pages = _docs_pages()
    assert pages, "no docs pages found"
    missing: list[str] = []
    for page in pages:
        front = _front_matter(_read(page))
        if front is None or "description:" not in front:
            missing.append(page.relative_to(PROJECT_ROOT).as_posix())
    assert missing == [], f"docs pages without a front-matter description: {missing}"


# --- root sitemap ------------------------------------------------------------


def test_root_sitemap_is_valid_xml_and_lists_docs() -> None:
    xml = _read(LANDING / "sitemap.xml")
    root = ET.fromstring(xml)
    locs = {node.text for node in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    assert "https://tancat.dev/docs/" in locs


# --- mobile nav --------------------------------------------------------------


def test_landing_has_a_reachable_mobile_menu() -> None:
    html = _read(LANDING / "index.html")
    assert 'id="mobile-nav"' in html
    assert "md:hidden" in html, "the desktop nav is hidden below md; a hamburger must show"
    for anchor in ("#how-it-works", "#pipeline", "#regulated", "#pricing"):
        assert f'href="{anchor}"' in html


# --- fonts are served from this site (t-1419) --------------------------------

#: Hosts that would see a visitor's IP address just for reading the page.
FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

#: The families the landing pages set in CSS. Each must resolve to a local file.
FONT_FAMILIES = ("Inter", "JetBrains Mono", "Newsreader")

FONTS_CSS = LANDING / "fonts.css"
FONTS_DIR = LANDING / "fonts"


def test_no_landing_page_requests_a_font_from_a_third_party() -> None:
    """The site's pitch is that your data stays with you, fonts included."""
    problems: list[str] = []
    for page in sorted(LANDING.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        for host in FONT_HOSTS:
            if host in html:
                problems.append(f"{page.name} still requests {host}")
        if "@import" in html and "font" in html.split("@import", 1)[1][:200].lower():
            problems.append(f"{page.name} uses an @import for a font - a third-party request before render")
    assert problems == [], "a landing page sends a visitor's IP to a font host:" + "\n  ".join(problems)


def test_the_landing_pages_link_the_self_hosted_stylesheet() -> None:
    for name in ("index.html", "install.html"):
        html = (LANDING / name).read_text(encoding="utf-8")
        assert 'href="fonts.css"' in html, f"{name} does not link the self-hosted fonts"


def test_every_font_the_stylesheet_sets_is_a_local_file() -> None:
    css = FONTS_CSS.read_text(encoding="utf-8")
    for family in FONT_FAMILIES:
        assert f"'{family}'" in css, f"fonts.css does not define {family}"

    referenced = re.findall(r"url\('fonts/([^']+)'\)", css)
    assert len(referenced) >= 6, f"fonts.css references only {len(referenced)} font files"
    missing = [name for name in referenced if not (FONTS_DIR / name).is_file()]
    assert missing == [], f"fonts.css points at files that do not exist: {missing}"

    for name in referenced:
        assert (FONTS_DIR / name).stat().st_size > 1000, f"{name} is empty or truncated"


def test_the_bundled_fonts_carry_their_licence_and_notice() -> None:
    """The OFL requires the licence to travel with the files."""
    licence = (FONTS_DIR / "OFL-1.1.md").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in licence, "the OFL text is missing from landing/fonts"
    for family in FONT_FAMILIES:
        assert family in licence, f"the licence notice does not name {family}"


def test_the_privacy_notice_no_longer_names_a_font_processor() -> None:
    html = (LANDING / "privacy.html").read_text(encoding="utf-8")
    assert "Google Fonts" not in html, "the privacy notice still names Google Fonts as a processor"
    assert "fonts are served from this site" in html, "the privacy notice does not say where the fonts come from"


def test_the_docs_theme_loads_no_third_party_fonts() -> None:
    """Material loads Roboto from Google by default; the theme's fonts are off."""
    config = yaml.safe_load(MKDOCS.read_text(encoding="utf-8"))
    theme = config["theme"]
    assert theme.get("font") is False, "the docs theme still loads its fonts from Google"

    extra_css = config.get("extra_css") or []
    assert "assets/fonts.css" in extra_css, "the docs site does not load the self-hosted fonts"

    css = (DOCS / "assets" / "fonts.css").read_text(encoding="utf-8")
    for host in FONT_HOSTS:
        assert host not in css, f"the docs stylesheet requests {host}"
    for family in ("Inter", "JetBrains Mono"):
        assert family in css, f"the docs stylesheet does not set {family}"
    # Material builds its stacks as var(--md-text-font,...), so the hook must be set;
    # --md-text-font-family alone loses to the theme's own body rule.
    assert "--md-text-font:" in css, "the docs stylesheet does not set the theme's text-font hook"
    assert "--md-code-font:" in css, "the docs stylesheet does not set the theme's code-font hook"
    for name in re.findall(r"/fonts/([a-z0-9-]+\.woff2)", css):
        assert (FONTS_DIR / name).is_file(), f"{name} is referenced but missing from landing/fonts"
