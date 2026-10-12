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
OG_SUBPAGES = ("install.html", "privacy.html", "terms.html")
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
