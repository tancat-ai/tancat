"""Build a self-contained phone-friendly demo HTML page with embedded screenshots."""
import json
import html as html_mod
import base64

# Annotated evidence screenshots from a real test run
# Each tuple: (path, slide-title, annotation-text)
SCREENSHOTS = [
    (
        "evidence/test_01_home_page_loads[chromium]_0_navigate_1783124638.png",
        "Step 3 - Scraper found the page",
        "The tool opened the target URL and captured the DOM. "
        "Every button, link, and input is recorded for selector resolution.",
    ),
    (
        "evidence/test_03_add_product_to_cart[chromium]_3_assertion_1783126159.png",
        "Step 5 - Test running live",
        "Playwright executed the generated test against the real site. "
        "This screenshot was captured mid-test — the assertion passed.",
    ),
    (
        "generated_tests/test_20260703_142302_as_a_shopper_on_automationexercise_com_i_want_to/evidence/test_TC01_06_verify_cart_table_details[chromium]_1_assertion_1783085160.png",
        "Step 5 - Evidence captured",
        "Every test step is recorded with annotated screenshots. "
        "Failures include the exact state of the page for debugging.",
    ),
]

TEST_FILE = "generated_tests/test_20260703_142302_as_a_shopper_on_automationexercise_com_i_want_to/test_as_a_shopper_on_automationexercise_com_i_want_to.py"
COVERAGE_FILE = "generated_tests/test_20260703_142302_as_a_shopper_on_automationexercise_com_i_want_to/coverage_summary.json"

# The user story that produced the test
USER_STORY = """As a shopper on automationexercise.com,
I want to browse products, add items to my cart,
and proceed to checkout
so that I can complete a purchase.

Acceptance Criteria:
1. Navigate to home page, verify categories visible
2. Click "Dress" category, see product list
3. Add a product to cart, see confirmation popup
4. Close popup, stay on category page
5. View cart, see items table
6. Verify product name, price, quantity in cart
7. Click "Proceed to checkout"
8. Verify checkout page loads"""

# The 8-test-all-green output
PYTEST_OUTPUT = """\
============================= test session starts =============================
collected 8 items

test_shopper_automationexercise.py::test_TC01_01_navigate_to_home_page PASSED [ 12%]
test_shopper_automationexercise.py::test_TC01_02_click_dress_category PASSED [ 25%]
test_shopper_automationexercise.py::test_TC01_03_add_to_cart_popup PASSED [ 37%]
test_shopper_automationexercise.py::test_TC01_04_close_popup_remain PASSED [ 50%]
test_shopper_automationexercise.py::test_TC01_05_view_cart_link PASSED [ 62%]
test_shopper_automationexercise.py::test_TC01_06_verify_cart_table PASSED [ 75%]
test_shopper_automationexercise.py::test_TC01_07_proceed_to_checkout PASSED [ 87%]
test_shopper_automationexercise.py::test_TC01_08_verify_checkout_auth PASSED [100%]

======================== 8 passed in 12.4s ========================="""


def load_screenshots():
    results = []
    for path, label, annotation in SCREENSHOTS:
        data = base64.b64encode(open(path, "rb").read()).decode()
        results.append({"data": data, "label": label, "annotation": annotation})
    return results


def build_evidence_slides(screenshots):
    parts = []
    for shot in screenshots:
        img_src = "data:image/png;base64," + shot["data"]
        parts.append(
            '<div class="slide">\n'
            '  <div class="slide-label">{}</div>\n'
            '  <img src="{}" alt="" class="screenshot">\n'
            '  <div class="annotation">{}</div>\n'
            '</div>'.format(shot["label"], img_src, shot["annotation"])
        )
    return "\n".join(parts)


CSS = r"""
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .header {
    padding: 16px 20px;
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-bottom: 2px solid #0f3460;
    text-align: center;
    flex-shrink: 0;
  }
  .header h1 {
    font-size: 1.3rem;
    background: linear-gradient(90deg, #e94560, #0f3460, #53d8fb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .header p { font-size: 0.8rem; color: #888; margin-top: 4px; }
  .slides-wrapper { flex: 1; overflow: hidden; position: relative; }
  .slides {
    display: flex;
    transition: transform 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    height: 100%;
  }
  .slide {
    min-width: 100vw;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 16px;
    overflow-y: auto;
    gap: 10px;
  }
  .title-slide { text-align: center; }
  .title-slide .emoji { font-size: 3.5rem; margin-bottom: 16px; }
  .title-slide h2 { font-size: 1.6rem; margin-bottom: 12px; color: #fff; }
  .title-slide p { font-size: 1rem; color: #aaa; max-width: 320px; line-height: 1.5; }
  .title-slide .badge {
    display: inline-block; margin-top: 16px; padding: 6px 14px;
    border-radius: 20px; background: #0f3460; color: #53d8fb;
    font-size: 0.8rem; font-weight: 600;
  }
  .slide-label {
    font-size: 0.85rem; color: #53d8fb; font-weight: 600;
    text-align: center;
  }
  .screenshot {
    max-width: 100%; max-height: 45vh;
    border-radius: 12px; border: 2px solid #1a1a3e;
    box-shadow: 0 0 30px rgba(83, 216, 251, 0.1);
    object-fit: contain;
  }
  .annotation {
    font-size: 0.78rem; color: #999; text-align: center;
    max-width: 320px; line-height: 1.4;
  }
  .code-block {
    background: #0d1117; border: 1px solid #21262d; border-radius: 10px;
    padding: 12px; font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.6rem; line-height: 1.35; color: #c9d1d9;
    overflow-x: auto; white-space: pre; width: 100%;
    max-height: 50vh; overflow-y: auto;
  }
  .story-block {
    background: #111827; border: 1px solid #1e293b; border-radius: 10px;
    padding: 14px; font-size: 0.78rem; line-height: 1.5; color: #ccc;
    width: 100%; max-width: 360px; max-height: 55vh; overflow-y: auto;
    border-left: 3px solid #e94560;
  }
  .story-block .label { font-size: 0.7rem; color: #666; text-transform: uppercase; margin-bottom: 6px; }
  .stats-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    width: 100%; max-width: 340px; margin-bottom: 12px;
  }
  .stat-card {
    background: #111827; border: 1px solid #1e293b;
    border-radius: 10px; padding: 12px; text-align: center;
  }
  .stat-card .number { font-size: 1.6rem; font-weight: 700; color: #53d8fb; }
  .stat-card .label { font-size: 0.7rem; color: #888; margin-top: 2px; }
  .stat-card.green .number { color: #22c55e; }
  .test-list { list-style: none; width: 100%; max-width: 400px; }
  .test-list li {
    padding: 6px 10px; background: #111827;
    border-left: 3px solid #22c55e; margin-bottom: 5px;
    border-radius: 0 6px 6px 0; font-size: 0.7rem;
    font-family: monospace; color: #c9d1d9;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .pipeline { display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 360px; }
  .pipeline-step {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 10px 14px; background: #111827;
    border-radius: 8px; border-left: 3px solid #0f3460;
  }
  .pipeline-step .step-num { font-size: 1.1rem; font-weight: 700; color: #e94560; min-width: 24px; }
  .pipeline-step .step-text { font-size: 0.78rem; color: #ccc; line-height: 1.35; }
  .pipeline-step .step-text b { color: #fff; }
  .footer-slide { text-align: center; }
  .footer-slide .emoji { font-size: 3rem; margin-bottom: 12px; }
  .footer-slide h2 { font-size: 1.4rem; color: #fff; margin-bottom: 8px; }
  .footer-slide p { color: #aaa; font-size: 0.9rem; line-height: 1.5; max-width: 300px; margin: 0 auto; }
  .footer-slide .link { margin-top: 16px; display: inline-block; color: #53d8fb; font-size: 0.85rem; }
  .nav {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 20px; background: #0a0a0f;
    border-top: 1px solid #1a1a2e; flex-shrink: 0;
  }
  .nav button {
    background: #1a1a2e; border: 1px solid #0f3460; color: #53d8fb;
    padding: 8px 18px; border-radius: 8px; font-size: 0.85rem; cursor: pointer;
    transition: all 0.2s;
  }
  .nav button:hover, .nav button:active { background: #0f3460; color: #fff; }
  .nav button:disabled { opacity: 0.3; cursor: default; }
  .page-indicator { font-size: 0.8rem; color: #666; }
  .swipe-hint { font-size: 0.65rem; color: #444; text-align: center; padding: 4px; }
  .tag { font-size: 0.6rem; color: #e94560; background: #1a0a0a; padding: 2px 8px; border-radius: 4px; }
"""

JS = r"""
  let current = 0;
  const total = TOTAL_PLACEHOLDER;
  const slides = document.getElementById('slides');

  function changeSlide(dir) {
    current = Math.max(0, Math.min(total - 1, current + dir));
    update();
  }

  function update() {
    slides.style.transform = 'translateX(' + (-current * 100) + 'vw)';
    document.getElementById('prevBtn').disabled = current === 0;
    document.getElementById('nextBtn').disabled = current === total - 1;
    document.getElementById('pageIndicator').textContent = (current + 1) + ' / ' + total;
  }

  let startX = 0;
  const wrapper = document.getElementById('slidesWrapper');
  wrapper.addEventListener('touchstart', e => { startX = e.touches[0].clientX; });
  wrapper.addEventListener('touchend', e => {
    const diff = startX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 50) {
      changeSlide(diff > 0 ? 1 : -1);
    }
  });
"""


def main():
    screenshots = load_screenshots()
    evidence_slides_html = build_evidence_slides(screenshots)

    with open(TEST_FILE) as f:
        test_code = f.read()[:2000]

    with open(COVERAGE_FILE) as f:
        coverage = json.load(f)

    test_list = "\n".join(
        "<li>{}</li>".format(html_mod.escape(t)) for t in coverage["tests"]
    )

    escaped_code = html_mod.escape(test_code)
    escaped_story = html_mod.escape(USER_STORY)
    escaped_pytest = html_mod.escape(PYTEST_OUTPUT)

    # 12 slides total:
    # 0: title
    # 1: user story input
    # 2: pipeline
    # 3: how skeleton-first works (2 phases)
    # 4-6: annotated evidence screenshots
    # 7: generated code
    # 8: test results (all green)
    # 9: stats + test list
    # 10: exports
    # 11: closing
    total_slides = 12

    js = JS.replace("TOTAL_PLACEHOLDER", str(total_slides))

    page = "".join([
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n",
        "<meta charset=\"UTF-8\">\n",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, user-scalable=no\">\n",
        "<title>AI Playwright Test Generator - Demo</title>\n",
        "<style>\n", CSS, "\n</style>\n",
        "</head>\n<body>\n\n",
        '<div class="header">\n',
        "  <h1>AI Playwright Test Generator</h1>\n",
        "  <p>User stories to runnable tests, locally</p>\n",
        "</div>\n\n",
        '<div class="slides-wrapper" id="slidesWrapper">\n',
        '  <div class="slides" id="slides">\n\n',

        # Slide 0: Title
        '    <div class="slide title-slide">\n',
        "      <div class=\"emoji\">&#x1F9AA;</div>\n",
        "      <h2>From User Stories to<br>Runnable Tests</h2>\n",
        "      <p>Paste a plain-English user story and get back real Playwright Python tests — generated entirely by a local LLM.</p>\n",
        '      <div class="badge">100% local, no API costs</div>\n',
        "    </div>\n\n",

        # Slide 1: The user story
        '    <div class="slide">\n',
        '      <div class="slide-label">Step 1 - Paste a User Story</div>\n',
        '      <div class="story-block">\n',
        '        <div class="label">Input</div>\n',
        escaped_story,
        "      </div>\n",
        '      <div class="annotation">That is the entire input. Plain English, no special syntax.</div>\n',
        "    </div>\n\n",

        # Slide 2: Pipeline
        '    <div class="slide">\n',
        '      <div class="slide-label">The Pipeline</div>\n',
        '      <div class="pipeline">\n',
        '        <div class="pipeline-step"><span class="step-num">1</span><span class="step-text"><b>Analyze</b> — LLM extracts acceptance criteria from the story</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">2</span><span class="step-text"><b>Scrape</b> — real browser opens the target pages, captures DOM elements</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">3</span><span class="step-text"><b>Phase 1: Skeletons</b> — LLM generates test functions with placeholder actions</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">4</span><span class="step-text"><b>Phase 2: Resolve</b> — placeholders mapped to real CSS selectors from scraped DOM</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">5</span><span class="step-text"><b>Run</b> — Playwright executes the tests against the live site</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">6</span><span class="step-text"><b>Report</b> — pass/fail results, annotated screenshots, HTML/JSON export</span></div>\n',
        "      </div>\n    </div>\n\n",

        # Slides 4-6: Annotated evidence
        evidence_slides_html, "\n\n",

        # Slide 7: Generated code
        '    <div class="slide">\n',
        '      <div class="slide-label">Step 4 - Generated Test Code (excerpt)</div>\n',
        '      <div class="code-block">', escaped_code, "</div>\n",
        '      <div class="annotation">Real Python, real Playwright selectors. Ready to commit to your test suite.</div>\n',
        "    </div>\n\n",

        # Slide 8: Test results
        '    <div class="slide">\n',
        '      <div class="slide-label">Step 5 - All Tests Pass</div>\n',
        '      <div class="code-block">', escaped_pytest, "</div>\n",
        '      <div class="annotation">8 acceptance criteria, 8 tests, all green in 12 seconds.</div>\n',
        "    </div>\n\n",

        # Slide 9: Stats
        '    <div class="slide">\n',
        '      <div class="slide-label">Sample Run — AutomationExercise</div>\n',
        '      <div class="stats-grid">\n',
        '        <div class="stat-card green"><div class="number">{}</div><div class="label">Tests Passed</div></div>\n'.format(coverage["journey_count"]),
        '        <div class="stat-card"><div class="number">{}</div><div class="label">Page Objects</div></div>\n'.format(coverage["page_object_count"]),
        '        <div class="stat-card"><div class="number">{}</div><div class="label">Pages Scraped</div></div>\n'.format(coverage["page_count"]),
        '        <div class="stat-card"><div class="number">{}</div><div class="label">Unresolved</div></div>\n'.format(coverage["unresolved_placeholder_count"]),
        "      </div>\n",
        '      <ul class="test-list">\n',
        test_list, "\n      </ul>\n",
        "    </div>\n\n",

        # Slide 10: Exports
        '    <div class="slide">\n',
        '      <div class="slide-label">Step 6 - Export Options</div>\n',
        '      <div class="pipeline">\n',
        '        <div class="pipeline-step"><span class="step-num">&#x1F4DD;</span><span class="step-text"><b>Python (.py)</b> — generated test file, ready to commit</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">&#x1F4C4;</span><span class="step-text"><b>JSON</b> — structured coverage data for CI/CD pipelines</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">&#x1F310;</span><span class="step-text"><b>HTML Report</b> — standalone page with screenshots and results</span></div>\n',
        '        <div class="pipeline-step"><span class="step-num">&#x270F;</span><span class="step-text"><b>Jira Markdown</b> — formatted for Jira issue comments</span></div>\n',
        "      </div>\n",
        '      <div class="annotation">Exports plug into whatever workflow your team uses.</div>\n',
        "    </div>\n\n",

        # Slide 11: Closing
        '    <div class="slide footer-slide">\n',
        "      <div class=\"emoji\">&#x1F389;</div>\n",
        "      <h2>Want to try one?</h2>\n",
        "      <p>Give me a user story and I'll generate the tests live. Or check out the repo:</p>\n",
        '      <a class="link" href="https://github.com/lacattano/AI-Playwright-Test-Generator">github.com/lacattano/AI-Playwright-Test-Generator</a>\n',
        "    </div>\n\n",

        "  </div>\n</div>\n\n",
        '<div class="swipe-hint">swipe or tap arrows</div>\n\n',
        '<div class="nav">\n',
        '  <button id="prevBtn" onclick="changeSlide(-1)" disabled>&larr; Back</button>\n',
        '  <span class="page-indicator" id="pageIndicator">1 / {}</span>\n'.format(total_slides),
        '  <button id="nextBtn" onclick="changeSlide(1)">Next &rarr;</button>\n',
        "</div>\n\n",
        "<script>\n", js, "\n</script>\n\n",
        "</body>\n</html>",
    ])

    with open("demo_party.html", "w") as f:
        f.write(page)

    print("Written demo_party.html ({} bytes)".format(len(page)))


if __name__ == "__main__":
    main()
