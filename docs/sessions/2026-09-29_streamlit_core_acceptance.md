# Streamlit core acceptance - 2026-09-29

**Job:** t-0097 (j-0023 follow-on). **Target:** the Streamlit app on
`http://localhost:8765/`. **Result: 14 of 14 criteria pass.**

## Recipe - what path, and why

The landing-page story (`scratch/landing_page_story.md`) was accepted with the
**generator pipeline** (`scratch/rerun_b065.py` / `scratch/session7_rerun.py` ->
`src.ui_pipeline.run_pipeline`: generate a suite, write the package, execute it
with pytest). That path is **not right for this job**: the core batch says "no
generated suite, no free-tier quota spent", and the generator is one of the
buttons that must not be pressed.

So this run uses the repo's **other established acceptance path - the live
replay** (`scratch/verify_b086_live.py`, `scratch/verify_b069b_live.py`): drive
the running page with Playwright, check each criterion directly, keep a
screenshot. Criterion 14 is a widget-state check, so it uses the repo's
existing Streamlit test path (`AppTest`, as in `tests/test_streamlit_*.py`).
No generated suite, no LLM, no forbidden button pressed.

## How the app was started

```
streamlit run streamlit_app.py --server.port 8765 --server.headless true
```

**Port caveat:** port 8765's IPv4 side is held by an unrelated `llmctl launcher`
(PID 20672). Streamlit bound the IPv6 side, so `http://localhost:8765/` reaches
Streamlit while `http://127.0.0.1:8765/` reaches the launcher. The launcher was
not touched. The run used `http://localhost:8765/`.

## Results

| # | Verdict | Criterion | Evidence |
|---|---|---|---|
| 1 | PASS | tab title | `TanCat - AI Playwright Test Generator` |
| 2 | PASS | TanCat heading | heading present |
| 3 | PASS | three nav links | `/`, `/run_fix_page`, `/evidence_page` |
| 4 | PASS | sidebar controls | `LLM Provider`, `Page Object Model`, `Provider Base URL`, `Model`, `Check My LLM` |
| 5 | PASS | licence line | `No license - running on the free tier.` |
| 6 | PASS | requirements options | `Paste Text`, `Upload File` |
| 7 | PASS | Requirements textarea | aria `Requirements`; placeholder starts `## User Story` |
| 8 | PASS | Run button present + enabled | present, enabled |
| 9 | PASS | Run & Fix heading + description | heading + exact description |
| 10 | PASS | no suite message | exact message |
| 11 | PASS | Evidence heading + description | heading + exact description |
| 12 | PASS | exactly three tabs | `Dashboard & Search`, `Coverage Heatmap`, `Gantt Timeline` |
| 13 | PASS | three export buttons (not pressed) | `CSV`, `NDJSON`, `JUnit XML` |
| 14 | PASS | Run button disabled after story typed | AppTest: empty `disabled=False`; after story `disabled=True` |

Full machine-readable results: `results.json`. Prose: `report.md`.

## Caveats

- **Criterion 14 via AppTest, not Playwright.** Headless Playwright does not
  reliably commit a Streamlit `text_area` value to the server (the widget value
  never reached `st.session_state`, so the live button stayed enabled). The app
  logic is `run_disabled = bool(raw_requirements.strip()) and not plan_confirmed`
  (`streamlit_app.py:617`); AppTest sets the widget value directly and confirms
  the button is disabled. The Playwright screenshot `14_story_typed.png` is kept
  as the visual record.
- **AppTest logged a benign lock.** `milvus_lite` reported
  `DataDirLockedError` on `evidence/rag_store.db` because the running app holds
  it. It does not affect the button-state check.
- Nothing was pressed that runs the generator, checks the LLM, deploys, prunes,
  loads or exports. The three export buttons were only counted.

## Screenshots

`docs/sessions/2026-09-29_streamlit_core_acceptance/screenshots/`

- `01_test_generator.png` - Test Generator page (criteria 1-8, 14)
- `09_run_fix.png` - Run & Fix page (criteria 9-10)
- `11_evidence.png` - Evidence & Reports page (criteria 11-12)
- `13_more_filters_expander.png` - the expanded export panel (criterion 13)
- `14_story_typed.png` - the story typed into the requirements box (criterion 14)
