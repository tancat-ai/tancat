# Demo Script — Show, Don't Tell (Phone Presentation)

This is a short, spoken script for presenting the product from a phone. No commands — just what you say, what to point at, and the visual cue the audience will see.

Length: 60–90 seconds (core demo) — extend to 2–3 minutes if you show run + report.

---

Start (5s)
- Hold the phone so the screen is visible. Smile and say: "Quick demo — one user story to runnable tests in under a minute." Pause 1s.

Introduce the story (10s)
- Tap the story box and say: "Here's a user story — I'll read it out loud." Read: "As a shopper on automationexercise.com, I want to add a product to my cart so I can proceed to checkout." Then say: "And three quick acceptance checks: product list visible, add to cart, cart shows item." Let the listener see the text for 2s.

Point to scraper results (8s)
- With a finger, open the "Scraper results" panel. Say: "The app inspected the page and found real elements — product titles, Add to cart buttons, and the cart link." Tap one scraped item and hold for 1s so they can read it.

Show the generated tests (10s)
- Switch to the code view and say: "Each acceptance check is a test — here are the generated skeletons. Simple, readable names, one test per criterion." Briefly scroll to show function names and one assertion line.

Run & react (15–30s)
- Press "Run" (or tap the Run panel) and say: "Now we run them — real browser, real results." Show the live output: green passes or the failing line. If passing, smile and say: "All green — reproducible checks we can commit." If failing, point to the stack trace and say: "Here's the failure and a screenshot to debug quickly."

Export & close (8s)
- Tap the download menu and say: "We can export the Python file, JSON for CI, or an HTML report to share with stakeholders." Show one downloaded filename briefly.

One-line close (4s)
- Say: "From plain English to runnable tests and shareable reports — that was under one minute. Want to try one together?"

---

Notes for tone and pacing
- Keep sentences short and declarative. Pause 1s after the headline lines so listeners register the claim.
- Use gestures: point to the story box, then to scraper results, then to code, then to run output, then to download.
- If the listener asks a question mid-demo, pause the demo, answer briefly, then continue.

Optional 2–3 minute extension
- After the close, show the `evidence/` screenshot gallery and mention integration: "The JSON report plugs into CI; the Python file is ready to commit." If they want technical detail, offer to run a second story.

---

Assets (optional)
- Add 3 phone-sized screenshots to `docs/assets/demo/`: story + scraper, generated code, run output. These are helpful when you can't run live.

---

I'll mark the demo script task complete and can update other demo docs or generate the phone screenshots next. 
