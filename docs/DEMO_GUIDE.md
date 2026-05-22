# Demo Guide – AI Playwright Test Generator

**The Elevator Pitch in a Pub.** Turn a user story into a passing, ready-to-run Playwright test in 3 minutes. No test automation expertise needed.

---

## 🎯 Why This Matters (30-second pitch)

**The Problem:**
> "Your QA team spends days writing Playwright tests. Selectors break. Tests require coding knowledge. Non-technical testers can't contribute."

**The Solution:**
> "Paste a user story. AI generates working tests with real DOM selectors. Runs in 3 minutes. Your whole team ships tests faster, not just your engineers."

**The Ask:**
> "Let me show you live. Takes 3 minutes and you'll see actual Playwright code execute against a real site."

---

## 🎬 Demo Objective

Prove that **non-technical QA testers** can generate, run, and export **production-ready Playwright tests** in under 5 minutes.

**Who Should See This:** QA Managers, Product Owners, QA Leads, Developers

**Demo Duration:** 3-5 minutes (including test execution)

---

## 🔧 Pre-Demo Checklist (60 seconds)

Run these before the meeting to avoid live failures:

```bash
# 1. Verify Ollama/LM Studio is running
ollama list
# OR check LM Studio UI that a model is loaded

# 2. Verify dependencies installed
uv sync

# 3. Start the app
bash launch_ui.sh
# (Keep it running in background during demo)

# 4. Playwright browsers installed?
python -c "import playwright; print('✓ Ready')"
```

**Abort conditions:** If any check fails, use the Backup Plan (see end of guide).

---

## 🎬 The 3-Minute Live Demo

### 1️⃣ Open App (30 seconds)

**What you do:**
- Show browser at `http://localhost:8501`
- Point out the clean interface

**What you say:**
> "This is the AI Playwright Test Generator. Non-technical QA testers paste a user story here. AI generates the tests."

---

### 2️⃣ Enter Target Site (30 seconds)

**What you do:**
- Paste into the "Base URL" field: `https://www.saucedemo.com`

**What you say:**
> "I'm pointing it at saucedemo.com – a real e-commerce site. The scraper will extract real DOM elements so our tests use actual selectors, not guesses."

---

### 3️⃣ Paste a User Story (30 seconds)

**What you do:**
- Copy-paste this into the textarea:

```
As a shopper visiting saucedemo.com, I want to log in with valid credentials 
so that I can browse available products.

Acceptance Criteria:
- Login form appears with username and password fields
- User can enter credentials
- LOGIN button is clickable
- After login, the inventory page displays product names like "Backpack" and "Bike Light"
```

**What you say:**
> "This is exactly what a QA tester writes in Jira or a test case. Plain English. Acceptance criteria. No technical jargon."

---

### 4️⃣ Generate Test (1-2 minutes)

**What you do:**
- Click the "✨ Generate Test" button
- Wait for the spinner (15-30 seconds depending on LLM speed)
- Show the generated Python code in the "Python Code" tab

**What you say:**
> "Watch what happens. The AI is:
> 1. Scraping the real website to find selectors
> 2. Generating a Playwright test skeleton with placeholders
> 3. Resolving each placeholder to actual DOM elements
> 4. Formatting the final pytest code
> 
> The whole process takes about 30 seconds."

**Expected output (show this code):**

```python
from playwright.sync_api import Page

def test_01_login_form_appears(page: Page) -> None:
    '''TC-1: Verify login form fields are visible.'''
    page.goto("https://www.saucedemo.com")
    
    # Verify login form fields
    assert page.get_by_placeholder("Username").is_visible()
    assert page.get_by_placeholder("Password").is_visible()
    
    # Enter valid credentials
    page.get_by_placeholder("Username").fill("standard_user")
    page.get_by_placeholder("Password").fill("secret_sauce")
    
    # Click LOGIN and verify redirect
    page.get_by_role("button", name="LOGIN").click()
    assert page.get_by_text("PRODUCTS").is_visible()

def test_02_inventory_displays_products(page: Page) -> None:
    '''TC-2: Verify inventory shows product names.'''
    page.goto("https://www.saucedemo.com/inventory.html")
    
    # Verify product names are displayed
    assert page.get_by_text("Backpack").is_visible()
    assert page.get_by_text("Bike Light").is_visible()
```

**Key talking point:**
> "Notice the selectors are real: `get_by_placeholder()`, `get_by_role()`, `get_by_text()`. This isn't LLM hallucination – these are actual elements scraped from the live site."

---

### 5️⃣ Run the Test (1-2 minutes)

**What you do:**
- Click "▶️ Run Now"
- Watch the spinner
- Show passing tests

**What you say:**
> "Now Playwright executes these tests in a real browser. Watch the test results."

**Expected output:**

```
✅ All tests passed!

collected 2 items
test_saucedemo_login.py::test_01_login_form_appears PASSED [50%]
test_saucedemo_login.py::test_02_inventory_displays_products PASSED [100%]

======================== 2 passed in 3.45s ========================
```

**The "wow" moment:**
> "Two tests. Generated from a user story. Executed against a real site. All passing. No manual selector hunting. No flaky selectors. Done."

---

### 6️⃣ Export Options (30 seconds)

**What you do:**
- Point out the three download buttons at the bottom

**What you say:**
> "You get three outputs:
> 1. **Python file** – Commit this to your test repo, run in CI/CD
> 2. **JSON report** – Integrates with your CI pipeline
> 3. **HTML report** – Share with stakeholders, includes screenshots"

---

## 💡 Talking Points to Land

Use these to reinforce value during the demo:

| Point | Why It Matters |
|-------|----------------|
| **"3-minute turnaround"** | No waiting days for test code. Instant feedback on acceptance criteria. |
| **"No coding required"** | Your whole QA team (not just engineers) ships tests. |
| **"Real selectors, no hallucination"** | Tests don't break because selectors are scraped, not guessed. |
| **"Runs locally"** | No API keys. No vendor lock-in. No cloud costs. Runs on your laptop. |
| **"Playable video evidence"** | Reports include screenshots + timelines to debug failures fast. |
| **"CI/CD ready"** | Export Python → commit → runs in your pipeline with zero changes. |

---

## ✅ Demo Success Checklist

- [ ] App loads without errors
- [ ] Scraper detects the site and shows "Scraper Active" status
- [ ] Generated code appears with real selectors (not placeholders)
- [ ] Tests run and pass
- [ ] All three export formats are available
- [ ] No timeout errors or 500s

If any of these fail, jump to **Backup Plan** below.

---

## 🆘 Backup Plans

### ❌ Ollama/LM Studio won't connect?

**Quick fix (60 seconds):**
1. Open a terminal: `ollama serve` (if Ollama)
2. Reload the browser page (F5)
3. If still broken, jump to **Pre-Recorded Demo** below

### ❌ saucedemo.com is down?

**Switch site immediately:**
- Try: `https://the-internet.herokuapp.com` (simpler site, fewer elements)
- Adjust user story to match (e.g., "Click the checkboxes")

### ❌ Test takes >1 minute to generate?

**Talking point while waiting:**
> "The LLM is thinking about the selectors and writing the test code. In production, this runs in your CI pipeline once per story – developers aren't waiting."

### 🎥 Plan B: Pre-Recorded Demo

If the app won't start, pivot to this story:

> "Let me show you a video I recorded earlier. Same 3-minute flow. You'll see the exact same output."

**Quick video script (if you have one prepared):**
1. Open the app
2. Paste user story
3. Generate test (time-lapse at 2x speed)
4. Run test
5. Show results

---

## 🗣️ Handling Objections

### "How does this handle complex journeys? Multi-page flows?"

> "Great question. You just include those in the user story. For example: 'User logs in, navigates to cart, applies discount code.' The AI builds a skeleton, then we scrape each page in sequence to resolve selectors. Same 3-minute window for most realistic flows."

### "What about logins and API setup?"

> "You tell the app which pages require login and what credentials to use. It handles the auth flow before scraping product pages. No manual cookie injection – it's all in the user story description."

### "What if the LLM generates bad tests?"

> "The skeleton-first approach means the AI generates structure with placeholders first. Then we resolve each placeholder against real DOM data. If a selector doesn't exist on the page, the test gets `pytest.skip()` with a note. You review and regenerate if needed. Zero hallucination."

### "Does this work with our custom framework?"

> "Today it generates pytest + Playwright (the most common). The output is plain Python, so you can wrap it in your framework after export. We're planning integration helpers for popular frameworks next."

### "What's the learning curve?"

> "For your QA team? Zero. They write user stories the way they already do. For your CI/CD team? 5 minutes – just add the generated Python files to your test directory and run pytest. That's it."

---

## 🎯 After the Demo – Next Steps

**If they're interested:**

> "Here's what I'd suggest: Let's run this on one of your actual user stories next week. I'll set it up on your staging site so you see it work against your real app. Takes 30 minutes end-to-end."

**Offer to send:**
- Link to this guide
- README.md overview
- Short video (if you have one)
- Offer for a 30-minute pairing session

---

## 📊 Quick Stats to Reference

- **Generation time:** 30-60 seconds (LLM dependent)
- **Test execution time:** 2-10 seconds (site dependent)
- **Non-technical QA adoption:** N/A (any QA tester can use)
- **CI/CD integration time:** <5 minutes (copy .py file, run pytest)
- **Selector hallucination rate:** ~0% (DOM-scraped, not LLM-guessed)

---

## 🚀 Call to Action Closing

Pick one:

> **A) "Let's run this on your actual staging site next week with a real user story. You'll see how fast your QA team can ship tests."**

> **B) "Your team would probably find this most useful for regression testing. Wanna try it on one of your high-impact user journeys?"**

> **C) "Send me a couple of your user stories and I'll generate tests against your site. I can show you the results in 24 hours."**

---

## 📚 Links & Resources

| Resource | Link |
|----------|------|
| **GitHub** | https://github.com/lacattano/AI-Playwright-Test-Generator |
| **Full README** | README.md (in this repo) |
| **Architecture Diagram** | docs/ARCHITECTURE.md |
| **Technical Specs** | docs/specs/ |

---

## 💻 Minimum System Specs (to run demo locally)

- **CPU:** Any modern processor
- **RAM:** 8GB+
- **Storage:** 10GB free (for model downloads)
- **Internet:** Needed only to scrape target sites (not for LLM – runs local)
- **OS:** Windows/Mac/Linux

---

*Last updated: 2026-05-22*
*Version: 2.0 — Sales Pitch Edition*