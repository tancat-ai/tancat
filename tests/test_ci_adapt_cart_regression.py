"""j-0312: the repair engine must repair the cart LINK, not the add-to-cart button.

This test uses the reviewer's hermetic-mock method: sabotage the generated
Cart-link step to ``a[href="/bogus.html"]``, then let the verified adaptation
engine scrape the real mock page, resolve the label and gate the patch. The
scorer used to rank a prominent "Add to cart" button above the cart anchor, so
the engine patched the wrong element, re-ran, failed and reverted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import action.adapt as adapt
from action.adapt import adapt_package

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _cart_package(tmp_path: Path, url: str) -> Path:
    pkg = tmp_path / "cart_pkg"
    (pkg / "pages").mkdir(parents=True)
    (pkg / "pages" / "home_page.py").write_text(
        "from playwright.sync_api import Page\n"
        "class HomePage:\n"
        "    def click_cart(self):\n"
        "        self.tracker.click('a[href=\"/bogus.html\"]', label='Cart')\n",
        encoding="utf-8",
    )
    (pkg / "test_main.py").write_text("def test_01(page):\n    pass\n", encoding="utf-8")
    (pkg / "package_manifest.json").write_text(json.dumps({"starting_url": url}), encoding="utf-8")
    (pkg / "evidence" / "test_01.evidence.json").parent.mkdir(parents=True, exist_ok=True)
    (pkg / "evidence" / "test_01.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "test_01", "status": "failed"},
                "steps": [
                    {
                        "label": "Cart",
                        "result": {
                            "status": "failed",
                            "error": "Locator 'a[href=\"/bogus.html\"]' not found on current page",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return pkg


def test_the_cart_link_repair_picks_the_cart_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mock_server import MockServer

    port = 8813
    with MockServer.start(port=port, directory=str(ROOT / "mock_sites" / "ecommerce")):
        url = f"http://127.0.0.1:{port}/index.html"
        pkg = _cart_package(tmp_path, url)
        junit = tmp_path / "junit.xml"
        junit.write_text(
            '<testsuite><testcase name="test_01">'
            "<failure message=\"Locator 'a[href=&quot;/bogus.html&quot;]' not found on current page\" />"
            "</testcase></testsuite>",
            encoding="utf-8",
        )
        monkeypatch.setattr(adapt, "run_single_test", lambda pkg, test, root: (0, "1 passed"))

        report = adapt_package(pkg, junit)

    assert report.summary["candidates"] == 1, report.to_dict()
    assert report.summary["adapted"] == 1, report.to_dict()
    assert report.summary["reverted"] == 0, report.to_dict()
    assert report.kept[0]["new_locator"] == 'a[href="/cart.html"]', report.to_dict()
    patched = (pkg / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert 'a[href="/cart.html"]' in patched
    assert 'a[href="/bogus.html"]' not in patched
    assert "add-to-cart" not in patched
