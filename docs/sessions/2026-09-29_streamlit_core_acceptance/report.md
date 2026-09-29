# Streamlit core acceptance - 2026-09-29T20:11:44

URL: http://localhost:8765/

1. **PASS** - tab title: title = 'TanCat - AI Playwright Test Generator'
2. **PASS** - TanCat heading: TanCat heading present: True
3. **PASS** - three nav links: nav = [('🧪\n\nTest Generator', 'http://localhost:8765/'), ('▶️\n\nRun & Fix', 'http://localhost:8765/run_fix_page'), ('📊\n\nEvidence & Reports', 'http://localhost:8765/evidence_page')]
4. **PASS** - sidebar controls: missing=[] check_my_llm_button=True
5. **PASS** - license line: sidebar has 'No license - running on the free tier.': True
6. **PASS** - requirements input options: radios = ['Paste Text', 'Upload File']
7. **PASS** - Requirements textarea: count=1 placeholder_starts='## User Story\nAs a customer I '
8. **PASS** - Run button present and enabled: present=True enabled=True
9. **PASS** - Run & Fix heading + description: heading=True description=True
10. **PASS** - no suite message: message_present=True
11. **PASS** - Evidence heading + description: heading=True description=True
12. **PASS** - exactly three tabs: tabs = ['📊 Dashboard & Search', '🌡️ Coverage Heatmap', '⏱️ Gantt Timeline']
13. **PASS** - three export buttons present (not pressed): export buttons = ['📥 CSV', '📥 NDJSON', '📥 JUnit XML']
14. **PASS** - Run button disabled after story typed: AppTest: empty disabled=False; after story disabled=True

**Passed 14 of 14.**

Screenshots: `scratch\streamlit_core_acceptance_2026-09-29\screenshots`
