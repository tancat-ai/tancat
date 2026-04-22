# Demo Guide â€” AI Playwright Test Generator

This guide provides a step-by-step walkthrough for demonstrating the AI Playwright Test Generator to stakeholders.

---

## ðŸŽ¯ Demo Objective

Show how non-technical QA testers can create automated Playwright tests from user stories in under 5 minutes using an LLM.

**Target Audience:** QA Managers, Product Owners, Developers, Technical Leads

**Demo Duration:** 4-5 minutes

---

## ðŸ“‹ Pre-Demo Checklist

Run these checks before the demo:

### 1. Verify Ollama is Running
```bash
ollama list
```
Expected output:
```
NAME                      SIZE      MODIFIED
qwen2.5-coder:1.5b        1.0 GB    2 minutes ago
llama3.2                  1.3 GB    1 hour ago
```

If no models are installed:
```bash
ollama pull qwen2.5-coder:1.5b
```

### 2. Verify Streamlit is Installed
```bash
streamlit --version
```
Expected output: `streamlit, version X.X.X`

### 3. Verify Playwright is Installed
```bash
python -c "import playwright; print(playwright.__version__)"
```
Expected output: A version number

### 4. Check Python Dependencies
```bash
pip list | grep -E "(streamlit|playwright|openai|pytest)"
```
All should show installed versions.

---

## ðŸŽ¬ Demo Script

### Step 1: Launch the Application (30 seconds)

**Terminal Command:**
```bash
streamlit run streamlit_app.py
```

**What Happens:**
- Browser opens automatically to `http://localhost:8501`
- Title displays: "ðŸŽ­ AI Playwright Test Generator"
- Dark terminal-themed UI loads

**Talking Points:**
> "This is the AI Playwright Test Generator. It allows non-technical QA testers to create automated tests from user stories."

---

### Step 2: Configure Base URL (30 seconds)

**UI Action:**
- In the sidebar, type or select: `https://www.saucedemo.com`

**Expected Display:**
```
âœ… Page Context Scraper Active
The scraper will attempt to scan the page at https://www.saucedemo.com to extract real DOM elements.
```

**Talking Points:**
> "Notice the scraper is active â€” it will extract real DOM elements from the page. This means the generated tests use actual selectors, not placeholder values."

---

### Step 3: Enter User Story (30 seconds)

**UI Action:**
- In the main panel, enter:

```markdown
As a visitor to saucedemo.com, I want to log in with valid credentials so that I can access the products page and see available items.

Acceptance Criteria:
- User should see login input fields for username and password
- User should be able to enter username and password
- User should see a LOGIN button
- Upon entering valid credentials, the user should be redirected to the inventory page
- The inventory page should display product cards with names like Backpack, Bike Light, etc.
```

**Talking Points:**
> "This is a typical user story from our backlog. Notice I'm using plain English with clear acceptance criteria. The AI will understand this format."

---

### Step 4: Generate Test (1-3 minutes depending on LLM speed)

**UI Action:**
- Click the "âœ¨ Generate Test" button

**What Happens:**
1. Page scraper activates (if URL was set)
2. LLM generates test code
3. Test is auto-saved to `generated_tests/` directory

**Expected Display:**
- Success toast: "âœ… Test generated successfully!"
- Code display with tabs for "Python Code" and "Preview"

**Expected Generated Test (similar to):**
```python
from playwright.sync_api import Page

def test_01_login_page_displayed(page: Page) -> None:
    '''TC-1: Verify login form is visible and user can enter credentials.'''
    page.goto("https://www.saucedemo.com")
    
    # Verify login form fields are present
    assert page.get_by_placeholder("Username").is_visible()
    assert page.get_by_placeholder("Password").is_visible()
    
    # Enter valid credentials
    page.get_by_placeholder("Username").fill("standard_user")
    page.get_by_placeholder("Password").fill("secret_sauce")
    
    # Click login button and verify redirect
    page.get_by_role("button", name="LOGIN").click()
    assert page.get_by_text("PRODUCTS").is_visible()
```

**Talking Points:**
> "The LLM has created a test based on my acceptance criteria. Notice it uses real selectors like `get_by_placeholder` and `get_by_role`. The test is automatically saved to disk."

---

### Step 5: Review Coverage Analysis (30 seconds)

**Expected Display:**
```
ðŸ“Š Coverage Analysis
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Overall Coverage            â”‚ 4/5   â”‚ 4         â”‚ 20%      â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚ â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–‘â–‘ 80%      â”‚ Coveredâ”‚ Tests      â”‚ Pending  â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**UI Action:**
- Click "ðŸ“‹ Detailed Coverage Report" to expand

**Expected Display:**
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Requirement                                                    â”‚ Status â”‚ Coverage â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚ Login form fields visible                                      â”‚ âœ…     â”‚ 100%     â”‚
â”‚ Enter username and password                                    â”‚ âœ…     â”‚ 100%     â”‚
â”‚ LOGIN button present                                           â”‚ âœ…     â”‚ 100%     â”‚
â”‚ Valid credentials redirect                                     â”‚ âœ…     â”‚ 100%     â”‚
â”‚ Inventory displays product cards                               â”‚ âš ï¸     â”‚ 60%      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

ðŸŽ¯ Generated Test Functions:
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ âœ“ test_01_login_page_displayed                                  â”‚
â”‚   - TC-1: Verify login form is visible                         â”‚
â”‚   - TC-2: User can enter username and password                 â”‚
â”‚   - TC-3: LOGIN button is present                              â”‚
â”‚   - TC-4: Redirect on valid credentials                        â”‚
â”‚                                                                 â”‚
â”‚ âœ“ test_02_inventory_displayed                                   â”‚
â”‚   - TC-5: Inventory displays product cards                     â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**Talking Points:**
> "Here's the coverage analysis. Each acceptance criterion maps to a test function. The confidence scores show how well each criterion is covered. The 'Pending' column shows what additional test coverage could be added."

---

### Step 6: Run the Test (1 minute)

**UI Action:**
- Click "â–¶ï¸ Run Now" button

**What Happens:**
1. Spinner displays: "Running tests..."
2. Playwright executes tests in headless browser
3. Results display with pass/fail status

**Expected Output (on success):**
```
âœ… All tests passed!

=== pytest test session starts =============================
collected 2 items

test_20260308_125114_as_a_visitor_to_saucedemo_com_i_want_to_log_in_wi.py::test_01_login_page_displayed PASSED [ 50%]
test_20260308_125114_as_a_visitor_to_saucedemo_com_i_want_to_log_in_wi.py::test_02_inventory_displayed PASSED [100%]

============================= 2 passed in 3.45s ==============================
```

**Expected Output (on failure - if site changes):**
```
âŒ Some tests failed

=== pytest test session starts =============================
collected 2 items

test_20260308_125114_as_a_visitor_to_saucedemo_com_i_want_to_log_in_wi.py::test_01_login_page_displayed PASSED [ 50%]
test_20260308_125114_as_a_visitor_to_saucedemo_com_i_want_to_log_in_wi.py::test_02_inventory_displayed FAILED [100%]

================================== FAILURES ==================================
______________________ test_02_inventory_displayed _________________________

page = <Page url='https://www.saucedemo.com/inventory.html'>

    def test_02_inventory_displayed(page: Page) -> None:
        page.goto("https://www.saucedemo.com/inventory.html")
>       assert page.get_by_text("Backpack").is_visible()
E       AssertionError: assert False
E        +  where False = is_visible()
E        +    where is_visible = <Playwright ElementHandle for text='Backpack'>.is_visible

    test_20260308_125114_as_a_visitor_to_saucedemo_com_i_want_to_log_in_wi.py:18: AssertionError
=========================== 1 failed, 1 passed in 2.10s ===========================
```

**Talking Points:**
> "Now we execute the test. Playwright runs it in a real browser and reports pass/fail. If there's a failure, we get detailed output with exact error locations. This feedback loop helps us improve our tests quickly."

---

### Step 7: Download Reports (30 seconds)

**UI Action:**
- Show the three download buttons at the bottom:

**Expected Buttons:**
1. **"ðŸ Python (.py)"** â€” Original test file with all imports and code
2. **"ðŸ“‹ JSON Report"** â€” Structured coverage data for CI/CD integration
3. **"ðŸŒ HTML Report"** â€” Standalone HTML report (can be opened in any browser)

**Expected Behavior:**
- Each button triggers a file download
- File names reflect the generated test name: `test_YYYYMMDD_HHMMSS_...`

**Talking Points:**
> "Finally, I can export the results in multiple formats. The Python file goes directly into our test repository. The JSON integrates with CI/CD pipelines. The HTML report is great for sharing with stakeholders."

---

## ðŸ“Š Demo Success Criteria

| Feature | Expected Result | Verification |
|---------|-----------------|--------------|
| Page scraper active | Green status box shows scraper info | âœ… |
| Test generation | Python code displayed in tab | âœ… |
| Coverage analysis | Metrics + detailed report expandable | âœ… |
| Test execution | Pass/Fail with pytest output | âœ… |
| Download options | 3 file formats available | âœ… |
| Auto-save | Test file appears in `generated_tests/` | âœ… |

---

## âš ï¸ Potential Issues & Mitigations

| Issue | Cause | Mitigation |
|-------|-------|------------|
| "No module named 'playwright'" | Playwright not installed | Run `uv sync` and then `playwright install chromium` before demo |
| "Ollama connection error" | Ollama not running | Start with `ollama serve` or check service |
| Timeout during generation | Model response is slower than timeout or prompt context is too large | Warm the model first, reduce scraped context size, or increase `OLLAMA_TIMEOUT` |
| Selector not found | saucedemo.com changed UI | Have backup test URL ready (e.g., staging) |
| Browser not found | Playwright browsers not installed | Run `playwright install chromium` |
| Port 8501 in use | Another Streamlit app running | Use different port: `streamlit run streamlit_app.py --server.port 8502` |

---

## ðŸ§ª Alternative Demo Sites

If saucedemo.com is unavailable, try:

| Site | URL | Note |
|------|-----|------|
| **DemoQA** | `https://demoqa.com` | Static demo site |
| **The Internet** | `https://the-internet.herokuapp.com` | Multiple testable features |
| **OrangeHRM** | `https://opensource-demo.orangehrmlive.com` | Enterprise app demo |

---

## ðŸ“ Quick Reference Commands

```bash
# Start demo
streamlit run streamlit_app.py

# Check Ollama models
ollama list

# Run a specific test
pytest generated_tests/test_*.py -v

# Install Playwright browsers
playwright install chromium

# Run with verbose output
streamlit run streamlit_app.py --server.enableCORS false
```

---

## ðŸŽ¤ Key Talking Points Summary

1. **"From user story to test in minutes"** â€” Highlight speed of workflow
2. **"No test automation knowledge required"** â€” Emphasize accessibility for non-developers
3. **"Real selectors, real tests"** â€” Explain scraper integration
4. **"Coverage tracking out of the box"** â€” Show requirement mapping
5. **"CI/CD ready outputs"** â€” Mention multiple export formats

---

## ðŸ“š Related Documentation

- [README.md](README.md) â€” Full project documentation
- [docs/specs/FEATURE_SPEC_page_context_scraper.md](docs/specs/FEATURE_SPEC_page_context_scraper.md) â€” Technical specifications
- [docs/PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md) â€” Implementation details
- [BACKLOG.md](BACKLOG.md) â€” Known issues and improvements

---

## ðŸŽ¬ Post-Demo Discussion Points

**Q: How does this integrate with existing CI/CD?**
> A: Export the JSON report for CI pipelines, or simply commit the generated Python test files to your repository.

**Q: What happens when the website changes?**
> A: Regenerate the test with updated user stories. The scraper will extract new selectors automatically.

**Q: Can this handle authenticated pages?**
> A: Yes. Use "Pages require login" with credential profiles and journey steps so scraping follows the authenticated path.

**Q: Does this work with any LLM?**
> A: Works with Ollama-hosted models. Configurable via `.env` file for OpenAI, Anthropic, etc.

---

*Last updated: 2026-03-31*
*Demo version: 1.1*
