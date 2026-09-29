"""Streamlit CORE acceptance (14 criteria) - live check against the running app.

Recipe note. The landing-page story (`scratch/landing_page_story.md`) was accepted
with the generator pipeline (`scratch/rerun_b065.py` -> `src.ui_pipeline.run_pipeline`:
generate a suite, then execute it). The CORE batch forbids that ("no generated
suite, no free-tier quota spent"), so this uses the repo's other established
acceptance path - the live replay (`scratch/verify_b086_live.py`,
`scratch/verify_b069b_live.py`): drive the running page with Playwright, check
each criterion directly, and keep a screenshot per criterion.

Presses nothing that runs the generator, checks the LLM, deploys, prunes, loads
or exports. Criterion 14 requires typing a story into the requirements box; the
Run button is read, never pressed.

Usage:
    streamlit run streamlit_app.py --server.port 8765 --server.headless true
    uv run python scratch/verify_streamlit_core_live.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

URL = "http://localhost:8765/"
OUT = Path("scratch/streamlit_core_acceptance_2026-09-29")
SHOTS = OUT / "screenshots"

# Criteria whose wording uses a plain hyphen while the app renders an em dash.
def _norm(text: str) -> str:
    return re.sub(r"[\u2010-\u2015]", "-", text)


def _links(page: Page) -> list[dict[str, str]]:
    return page.eval_on_selector_all(
        "a", "els => els.map(e => ({t: e.innerText.trim(), h: e.getAttribute('href')}))"
    )


def _buttons(page: Page) -> list[str]:
    return [b.strip() for b in page.eval_on_selector_all("button", "els => els.map(e => e.innerText.trim())")]


def _criterion_14_apptest() -> tuple[bool, str]:
    """Criterion 14 via the repo's AppTest path (tests/test_streamlit_*.py).

    Headless Playwright does not reliably commit a Streamlit text_area value to
    the server, so the widget-state criterion is checked the way this repo
    already tests Streamlit widget state.
    """
    from unittest.mock import MagicMock, patch

    from streamlit.testing.v1 import AppTest

    app_path = str(Path("streamlit_app.py").resolve())
    mock_llm = MagicMock()
    mock_llm.generate = MagicMock(return_value="")
    mock_llm.list_models = MagicMock(return_value=[])

    def _fake_exists(self: Path) -> bool:
        return False

    with patch("streamlit_app.LLMClient", new=mock_llm), patch.object(Path, "exists", _fake_exists):
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run(timeout=30)
        before = [b for b in at.button if b.label == "Run Intelligent Pipeline"][0].disabled
        [t for t in at.text_area if t.key == "requirements_text"][0].set_value(
            "As a customer I want to add items to cart."
        )
        at.run(timeout=30)
        after = [b for b in at.button if b.label == "Run Intelligent Pipeline"][0].disabled
    return (not before) and after, f"AppTest: empty disabled={before}; after story disabled={after}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    def record(n: int, criterion: str, verdict: str, evidence: str, shot: str = "") -> None:
        results.append({"n": n, "criterion": criterion, "verdict": verdict, "evidence": evidence, "screenshot": shot})
        print(f"[{verdict.upper():4}] {n:>2}. {evidence}")

    def shot(page: Page, name: str) -> str:
        path = SHOTS / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})

        # ---------- Test Generator page ----------
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("text=TanCat", timeout=60000)
        page.wait_for_timeout(4000)
        body = page.inner_text("body")
        sidebar = page.inner_text("[data-testid='stSidebar']")
        main_shot = shot(page, "01_test_generator")

        title = _norm(page.title().strip())
        want_title = "TanCat - AI Playwright Test Generator"
        record(1, "tab title", "pass" if title == want_title else "fail", f"title = {title!r}", main_shot)

        headings = [h.strip() for h in page.eval_on_selector_all("h1,h2,h3", "els => els.map(e => e.innerText.trim())")]
        has_tancat = any(h == "TanCat" for h in headings)
        record(
            2,
            "TanCat heading",
            "pass" if has_tancat else "fail",
            f"TanCat heading present: {has_tancat}",
            main_shot,
        )

        nav = [(l["t"], l["h"] or "") for l in _links(page) if (l["h"] or "").startswith(URL)]
        paths = sorted(h.replace(URL, "/") for _t, h in nav)
        nav_ok = paths == ["/", "/evidence_page", "/run_fix_page"] and len(nav) == 3
        record(3, "three nav links", "pass" if nav_ok else "fail", f"nav = {nav}", main_shot)

        controls = ["LLM Provider", "Page Object Model", "Provider Base URL", "Model"]
        missing = [c for c in controls if c not in sidebar]
        has_check = any("Check My LLM" in b for b in _buttons(page))
        record(
            4,
            "sidebar controls",
            "pass" if not missing and has_check else "fail",
            f"missing={missing} check_my_llm_button={has_check}",
            main_shot,
        )

        line = "No license - running on the free tier."
        record(
            5,
            "license line",
            "pass" if line in _norm(sidebar) else "fail",
            f"sidebar has {line!r}: {line in _norm(sidebar)}",
            main_shot,
        )

        radios = [r.strip() for r in page.eval_on_selector_all("[role='radiogroup'] label", "els => els.map(e => e.innerText.trim())")]
        record(
            6,
            "requirements input options",
            "pass" if radios == ["Paste Text", "Upload File"] else "fail",
            f"radios = {radios}",
            main_shot,
        )

        ta = page.locator("textarea[aria-label='Requirements']")
        ph = ta.get_attribute("placeholder") or "" if ta.count() else ""
        record(
            7,
            "Requirements textarea",
            "pass" if ta.count() == 1 and ph.startswith("## User Story") else "fail",
            f"count={ta.count()} placeholder_starts={ph[:30]!r}",
            main_shot,
        )

        run_btn = page.get_by_role("button", name="Run Intelligent Pipeline")
        present = run_btn.count() == 1
        enabled = present and run_btn.is_enabled()
        record(
            8,
            "Run button present and enabled",
            "pass" if present and enabled else "fail",
            f"present={present} enabled={enabled}",
            main_shot,
        )

        # Criterion 14: a widget-state check, via the repo's AppTest path.
        ta.fill("As a customer I want to add items to cart.")
        page.wait_for_timeout(1500)
        shot14 = shot(page, "14_story_typed")
        c14_ok, c14_evidence = _criterion_14_apptest()
        record(
            14,
            "Run button disabled after story typed",
            "pass" if c14_ok else "fail",
            c14_evidence,
            shot14,
        )

        # ---------- Run & Fix page ----------
        page.goto(URL + "run_fix_page", wait_until="domcontentloaded")
        page.wait_for_selector("text=Run the current suite", timeout=60000)
        page.wait_for_timeout(2500)
        rf = page.inner_text("body")
        rf_shot = shot(page, "09_run_fix")
        desc9 = "Run the current suite, fix failing/skipped tests, and review this run's evidence."
        record(
            9,
            "Run & Fix heading + description",
            "pass" if "Run & Fix" in rf and desc9 in rf else "fail",
            f"heading={'Run & Fix' in rf} description={desc9 in rf}",
            rf_shot,
        )
        msg10 = "No current suite loaded. Generate tests on the Test Generator page, or load a saved package from the sidebar."
        record(10, "no suite message", "pass" if msg10 in rf else "fail", f"message_present={msg10 in rf}", rf_shot)

        # ---------- Evidence & Reports page ----------
        page.goto(URL + "evidence_page", wait_until="domcontentloaded")
        page.wait_for_selector("text=Annotated test journeys", timeout=60000)
        page.wait_for_timeout(2500)
        ev = page.inner_text("body")
        ev_shot = shot(page, "11_evidence")
        desc11 = "Annotated test journeys, Gantt timelines, coverage heatmaps, and run history."
        record(
            11,
            "Evidence heading + description",
            "pass" if "Evidence & Reports" in ev and desc11 in ev else "fail",
            f"heading={'Evidence & Reports' in ev} description={desc11 in ev}",
            ev_shot,
        )
        tabs = [t.strip() for t in page.eval_on_selector_all("[role='tab']", "els => els.map(e => e.innerText.trim())")]
        want_tabs = ["Dashboard & Search", "Coverage Heatmap", "Gantt Timeline"]
        tabs_ok = len(tabs) == 3 and all(w in " ".join(tabs) for w in want_tabs)
        record(12, "exactly three tabs", "pass" if tabs_ok else "fail", f"tabs = {tabs}", ev_shot)

        # Criterion 13: expand "More filters & export" (an expander, not an export
        # button). Streamlit download buttons render under stDownloadButton with
        # an icon prefix ("CSV" -> "📥 CSV").
        expander = page.locator("details", has_text="More filters & export").first
        if expander.count():
            expander.locator("summary").first.click()
            page.wait_for_timeout(1500)
        export_labels = (
            [t.strip() for t in expander.locator("[data-testid='stDownloadButton']").all_inner_texts()]
            if expander.count()
            else []
        )
        export_ok = (
            len(export_labels) == 3
            and any("CSV" in t for t in export_labels)
            and any("NDJSON" in t for t in export_labels)
            and any("JUnit XML" in t for t in export_labels)
        )
        shot13 = shot(page, "13_more_filters_expander")
        record(
            13,
            "three export buttons present (not pressed)",
            "pass" if export_ok else "fail",
            f"export buttons = {export_labels}",
            shot13,
        )

        browser.close()

    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "url": URL,
        "criteria": sorted(results, key=lambda r: r["n"]),
        "passed": sum(1 for r in results if r["verdict"] == "pass"),
        "total": len(results),
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Streamlit core acceptance - {payload['run_at']}", "", f"URL: {URL}", ""]
    for r in payload["criteria"]:
        lines.append(f"{r['n']}. **{r['verdict'].upper()}** - {r['criterion']}: {r['evidence']}")
    lines += ["", f"**Passed {payload['passed']} of {payload['total']}.**", "", f"Screenshots: `{SHOTS}`"]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nRESULT: {payload['passed']} of {payload['total']} passed")
    print(f"Report: {OUT / 'report.md'}")
    print(f"Screenshots: {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
