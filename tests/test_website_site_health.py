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


# --- nothing on this site loads a resource from another host (t-1419, t-1421) --

FONTS_CSS = LANDING / "fonts.css"
FONTS_DIR = LANDING / "fonts"
OVERRIDES = PROJECT_ROOT / "overrides"

#: The two families the pages actually use. Newsreader was declared in the original
#: @import but no page sets serif text, so it was never fetched (t-1421 removed it).
FONT_FAMILIES = ("Inter", "JetBrains Mono")

#: The copyright line each family carries, as the font's own metadata gives it.
FONT_COPYRIGHTS = {
    "Inter": "Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)",
    "JetBrains Mono": "Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)",
}

#: This site. A resource may point here, or at a path with no host at all.
OWN_HOSTS = ("tancat.dev", "www.tancat.dev")

#: Elements whose attribute makes the browser fetch something. An <a href> is a
#: navigation the reader chooses, so it is deliberately not in this list.
RESOURCE_TAGS = ("link", "script", "img", "iframe", "source", "video", "audio")

TAG = re.compile(r"<(link|script|img|iframe|source|video|audio)\b([^>]*)>", re.IGNORECASE)
ATTR = re.compile(r"""\b(src|href|poster|data-src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
REL = re.compile(r"""\brel\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
CSS_URL = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.IGNORECASE)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)", re.IGNORECASE)

#: A link rel that is metadata or navigation, not a fetch.
NON_FETCH_REL = ("canonical", "alternate", "author", "license", "next", "prev", "me")


def resource_sources() -> list[Path]:
    """Every file that can make a browser fetch something."""
    files: list[Path] = [
        *sorted(LANDING.glob("*.html")),
        *sorted(DOCS.rglob("*.md")),
        *sorted(OVERRIDES.rglob("*.html")),
        *sorted(LANDING.glob("*.css")),
        *sorted((DOCS / "assets").glob("*.css")),
        MKDOCS,
    ]
    return [path for path in files if path.is_file()]


def urls_loaded_by(path: Path) -> list[str]:
    """The URLs *path* makes a browser fetch, in order."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[str] = []

    if path.suffix == ".md":
        found.extend(match.group(1) for match in MD_IMAGE.finditer(text))

    if path.suffix in {".html", ".md"}:
        for tag, attrs in TAG.findall(text):
            rel = REL.search(attrs)
            if tag.lower() == "link" and rel and any(word in rel.group(1).lower() for word in NON_FETCH_REL):
                continue
            for attr, value in ATTR.findall(attrs):
                if tag.lower() == "script" and attr.lower() != "src":
                    continue
                found.append(value)

    if path.suffix == ".css":
        found.extend(match.group(1) for match in CSS_URL.finditer(text))

    if path.name == "mkdocs.yml":
        config = yaml.safe_load(text)
        theme = config.get("theme") or {}
        for key in ("favicon", "logo"):
            value = theme.get(key)
            if isinstance(value, str):
                found.append(value)
        for key in ("extra_css", "extra_javascript"):
            for entry in config.get(key) or []:
                found.append(entry if isinstance(entry, str) else str(entry.get("path", "")))

    return [url.strip() for url in found if url and url.strip()]


def external_host(url: str) -> str | None:
    """The host a URL points at, or None when it stays on this site."""
    low = url.lower()
    if low.startswith(("data:", "#", "mailto:", "tel:", "javascript:", "about:")):
        return None
    if low.startswith("//"):
        return url[2:].split("/", 1)[0]
    match = re.match(r"^[a-z][a-z0-9+.-]*://([^/]+)", url, re.IGNORECASE)
    if not match:
        return None  # relative or site-absolute path
    host = match.group(1).split(":", 1)[0].lower()
    return None if host in OWN_HOSTS else host


def test_nothing_on_this_site_loads_a_resource_from_another_host() -> None:
    """Not 'no Google font' - no third-party resource at all, whatever the host."""
    sources = resource_sources()
    assert len(sources) >= 20, f"the scan found only {len(sources)} files - it is not seeing the site"

    problems: list[str] = []
    for path in sources:
        for url in urls_loaded_by(path):
            host = external_host(url)
            if host is not None:
                problems.append(f"{path.relative_to(PROJECT_ROOT)} loads {url} from {host}")

    assert problems == [], "a page loads a resource from another host:\n  " + "\n  ".join(problems)


def test_the_resource_scan_covers_every_kind_of_page() -> None:
    names = {path.name for path in resource_sources()}
    for required in ("index.html", "install.html", "404.html", "fonts.css", "mkdocs.yml"):
        assert required in names, f"the resource scan does not cover {required}"


def test_the_landing_pages_link_the_self_hosted_stylesheet() -> None:
    for name in ("index.html", "install.html"):
        html = (LANDING / name).read_text(encoding="utf-8")
        assert 'href="fonts.css"' in html, f"{name} does not link the self-hosted fonts"


def test_every_font_the_stylesheet_sets_is_a_local_file() -> None:
    css = FONTS_CSS.read_text(encoding="utf-8")
    for family in FONT_FAMILIES:
        assert f"'{family}'" in css, f"fonts.css does not define {family}"

    referenced = re.findall(r"url\('fonts/([^']+)'\)", css)
    assert len(referenced) == len(FONT_FAMILIES), (
        f"fonts.css references {len(referenced)} files for {len(FONT_FAMILIES)} families"
    )
    missing = [name for name in referenced if not (FONTS_DIR / name).is_file()]
    assert missing == [], f"fonts.css points at files that do not exist: {missing}"

    on_disk = sorted(path.name for path in FONTS_DIR.glob("*.woff2"))
    assert on_disk == sorted(referenced), (
        f"landing/fonts holds files no stylesheet fetches: {sorted(set(on_disk) - set(referenced))}"
    )

    for name in referenced:
        assert (FONTS_DIR / name).stat().st_size > 1000, f"{name} is empty or truncated"


def test_the_font_notice_describes_the_files_it_ships() -> None:
    """The OFL requires the licence to travel with the files, and it must be true."""
    licence = (FONTS_DIR / "OFL-1.1.md").read_text(encoding="utf-8")
    readme = (FONTS_DIR / "README.md").read_text(encoding="utf-8")

    assert "SIL OPEN FONT LICENSE" in licence, "the OFL text is missing from landing/fonts"
    for family, copyright_line in FONT_COPYRIGHTS.items():
        assert family in licence, f"the licence notice does not name {family}"
        assert copyright_line in licence, f"the licence notice does not carry {family}'s own copyright line"
        assert copyright_line in readme, f"the README does not carry {family}'s own copyright line"
    assert "Newsreader" not in licence, "the notice still names a family that is not shipped"

    for sentence in ("Both families are licensed", "Google Fonts serves"):
        assert sentence in licence, f"the notice does not say {sentence!r}"
    assert "repositories" not in licence, "the notice still claims the files come from the font repositories"


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
    for family in FONT_FAMILIES:
        assert family in css, f"the docs stylesheet does not set {family}"
    # Material builds its stacks as var(--md-text-font,...), so the hook must be set;
    # --md-text-font-family alone loses to the theme's own body rule.
    assert "--md-text-font:" in css, "the docs stylesheet does not set the theme's text-font hook"
    assert "--md-code-font:" in css, "the docs stylesheet does not set the theme's code-font hook"
    for name in re.findall(r"/fonts/([a-z0-9-]+\.woff2)", css):
        assert (FONTS_DIR / name).is_file(), f"{name} is referenced but missing from landing/fonts"
