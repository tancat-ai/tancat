# Feature Spec — Evidence Search, Filter & Export

**Feature ID:** AI-028
**Created:** 2026-07-19
**Status:** Draft
**Priority:** Medium (Tier 2 — Feature Completion)
**Depends on:** AI-012 (SQLite Persistence, shipped), AI-011 (Run History Chart, shipped)

---

## 1. Problem Statement

The evidence viewer and run history currently lock data inside the tool. Users have accumulated weeks of test evidence (50+ test packages, hundreds of sidecars) but face two problems:

### Lock-in problem
Evidence lives in project-specific formats (`.evidence.json` sidecars, `run_results.sqlite`) that can only be consumed through the Streamlit UI. Users cannot:
- Open test results in Excel, Tableau, or Datadog
- Feed evidence into their existing CI/CD dashboards
- Query evidence with `jq`, pandas, or SQL outside the project

### Discoverability problem
Even within the tool, the evidence viewer shows all historical evidence in a flat `st.selectbox` dropdown sorted only by file modification time. Users cannot:
- Find specific tests — e.g. "show me all tests on `automationexercise.com` that involve dresses"
- Filter by criteria — e.g. "only show TC01.xx tests" or "only failed evidence"
- Search by step content — e.g. "tests that clicked a login button"
- Cross-reference requirements — e.g. "what evidence exists for story S06?"

---

## 2. Philosophy: Export-First, Search as Convenience

The **primary deliverable** is standard-format exports that let users take their data anywhere. The in-tool search UI is a **convenience layer** — useful for quick lookups during development, but not a replacement for the user's existing toolchain. Every piece of evidence the tool produces should be exportable in formats that Excel, pandas, Datadog, Splunk, Tableau, or any BI tool can consume without any dependency on this project.

---

## 3. Goals

| # | Goal | Criteria |
|---|------|----------|
| 1 | **CSV export** | One flat CSV per export scope (all evidence, filtered subset, per test package). Columns: test_name, condition_ref, story_ref, status, page_url, step_count, step_types, step_labels_joined, duration_s, test_package, sidecar_path. Openable in Excel, pandas, Tableau with zero config. |
| 2 | **NDJSON export** | One JSON object per evidence sidecar per line. Full sidecar data including step-level detail. Ingestible by Splunk, Elasticsearch, `jq`, pandas `read_json(lines=True)`. |
| 3 | **JUnit XML export** | Standard CI/CD format. Test suite → test cases with status, duration, failure messages. Consumable by Jenkins, GitHub Actions, GitLab CI, TestRail, Allure. |
| 4 | **Full-text search (in-tool)** | Type a query and filter evidence sidecars by test name, condition ref, story ref, URL, step labels. Convenience for quick lookups — not the primary interface. |
| 5 | **Faceted filters (in-tool)** | Dropdown/multiselect filters for: URL/domain, status (passed/failed), condition ref prefix. |
| 6 | **Fast startup** | Indexing must not block UI load — scan and index evidence metadata lazily or via file-mtime incremental refresh. |
| 7 | **SQLite-backed index** | Store evidence metadata in a new table (`evidence_index`) in the existing `evidence/run_results.sqlite`. Powers both in-tool search and CSV/NDJSON export queries. |
| 8 | **Backwards compatible** | Existing evidence sidecars load without migration. Index is built/refreshed from files on disk. |

---

## 4. Non-Goals

- Full-text search inside PNG screenshots (OCR) — out of scope
- Real-time index updates during test execution (rebuild on UI load or manual refresh is sufficient)
- Building a full analytics dashboard — export formats enable users to use their own tools for that
- REST API for search (future consideration — see FC-01 in roadmap)
- Migrating the `.evidence.json` files themselves into SQLite (screenshots stay on disk)

---

## 5. Export Formats

All exports read from the same `evidence_index` SQLite table that powers in-tool search. Filtering is consistent across all export formats and the search UI.

### 5.1 CSV Export (`evidence_export.csv`)

Flat table, one row per evidence sidecar. Designed for Excel, pandas, Tableau.

```csv
test_name,condition_ref,story_ref,status,page_url,step_count,step_types,step_labels,duration_s,test_package,sidecar_path
test_cart_products[chromium],TC01.06,S06,failed,https://automationexercise.com/view_cart,2,navigate|assertion,"Navigate to https://...|cart product table",2.34,test_20260719_224736...,test_20260719_.../evidence/test_cart...[chromium].evidence.json
test_view_cart[chromium],TC01.05,S06,passed,https://automationexercise.com/view_cart,3,navigate|assertion|assertion,"Navigate to...|cart visible|item count correct",1.89,test_20260719_224736...,test_20260719_.../evidence/test_view_cart...[chromium].evidence.json
```

| Column | Source |
|--------|--------|
| `test_name` | `sidecar.test.name` |
| `condition_ref` | `sidecar.test.condition_ref` |
| `story_ref` | `sidecar.test.story_ref` |
| `status` | `sidecar.test.status` |
| `page_url` | `sidecar.page.url` |
| `step_count` | `len(sidecar.steps)` |
| `step_types` | Pipe-joined `sidecar.steps[].type` |
| `step_labels` | Pipe-joined `sidecar.steps[].label` |
| `duration_s` | `sidecar.test.duration_s` (if present) |
| `test_package` | Parent `test_*` directory name |
| `sidecar_path` | Relative path from `generated_tests/` |

**Export triggers:**
- Streamlit download button in evidence viewer (full dataset or search-filtered subset)
- CLI: `python -m cli.evidence_export --format csv --output evidence.csv`
- CLI with filters: `python -m cli.evidence_export --format csv --status failed --domain automationexercise.com`

### 5.2 NDJSON Export (`evidence_export.ndjson`)

One JSON object per line — the full sidecar data. Designed for log ingestion, `jq`, pandas.

```jsonl
{"test":{"name":"test_cart_products...[chromium]","condition_ref":"TC01.06","story_ref":"S06","status":"failed"},"page":{"url":"https://automationexercise.com/view_cart"},"steps":[{"type":"navigate","label":"Navigate to...","value":"https://..."},{"type":"assertion","label":"cart product table","value":null}]}
{"test":{"name":"test_view_cart...[chromium]","condition_ref":"TC01.05","story_ref":"S06","status":"passed"},"page":{"url":"https://automationexercise.com/view_cart"},"steps":[...]}
```

**Consumption examples:**
```bash
# jq: count failed tests
cat evidence.ndjson | jq 'select(.test.status=="failed")' | wc -l

# pandas: load into DataFrame
import pandas as pd
df = pd.read_json('evidence.ndjson', lines=True)

# Splunk: one-shot upload or monitored input
```

### 5.3 JUnit XML Export (`evidence_junit.xml`)

Standard CI/CD test report format. One `<testsuite>` per export, one `<testcase>` per evidence sidecar.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="evidence_export" tests="42" failures="3" errors="0" skipped="0" time="98.4">
    <testcase classname="automationexercise.view_cart" name="TC01.06_cart_products_displayed" time="2.34">
      <failure message="cart product table not visible">Assertion failed: element not found</failure>
    </testcase>
    <testcase classname="automationexercise.view_cart" name="TC01.05_view_cart" time="1.89" />
  </testsuite>
</testsuites>
```

| XML attribute | Source |
|---------------|--------|
| `classname` | `domain.page_path` extracted from `page_url` |
| `name` | `{condition_ref}_{test_name_slug}` |
| `time` | `duration_s` (or `0.0` if not recorded) |
| `<failure>` | Present if `status == "failed"`, contains first step error message |

**CI/CD integration:** Drop the XML into any JUnit-compatible tool — Jenkins `junit` publisher, GitHub Actions `dorny/test-reporter`, GitLab CI `reports:junit`, TestRail, Allure.

---

## 6. Architecture

### 6.1 Evidence Sidecar Metadata (fields to index)

Each `.evidence.json` sidecar contains:

```json
{
  "schema_version": "1.0",
  "test": {
    "name": "test_cart_products_displayed_correctly[chromium]",
    "condition_ref": "TC01.06",
    "story_ref": "S06",
    "status": "failed"
  },
  "page": {
    "url": "https://automationexercise.com/view_cart"
  },
  "steps": [
    {
      "type": "navigate",
      "label": "Navigate to https://automationexercise.com/view_cart",
      "value": "https://automationexercise.com/view_cart"
    },
    {
      "type": "assertion",
      "label": "cart product table",
      "value": null
    }
  ]
}
```

Searchable fields:
- `test.name` — test function name
- `test.condition_ref` — e.g. `TC01.06`
- `test.story_ref` — e.g. `S06`
- `test.status` — `passed` | `failed`
- `page.url` — navigated URL
- `steps[].label` — step description text (e.g. "cart product table", "Navigate to ...")
- `steps[].type` — `navigate` | `click` | `fill` | `assertion` | `select`

### 6.2 Database Schema Addition

New table in `evidence/run_results.sqlite` (alongside existing `runs` and `test_results`):

```sql
CREATE TABLE IF NOT EXISTS evidence_index (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sidecar_path    TEXT    NOT NULL UNIQUE,   -- relative path from generated_tests/
    test_name       TEXT    NOT NULL,
    condition_ref   TEXT,                      -- e.g. TC01.06
    story_ref       TEXT,                      -- e.g. S06
    status          TEXT    NOT NULL,          -- passed | failed
    page_url        TEXT,                      -- navigated URL (domain extractable)
    step_labels     TEXT,                      -- concatenated step labels for full-text search
    step_types      TEXT,                      -- concatenated step types (navigate,click,fill,assertion,select)
    test_package    TEXT    NOT NULL,          -- parent test_* directory name
    file_mtime      REAL    NOT NULL,          -- OS mtime of sidecar file (for staleness detection)
    indexed_at      TEXT    NOT NULL            -- ISO-8601 when this row was created/updated
);

CREATE INDEX IF NOT EXISTS idx_evidence_status ON evidence_index(status);
CREATE INDEX IF NOT EXISTS idx_evidence_condition_ref ON evidence_index(condition_ref);
CREATE INDEX IF NOT EXISTS idx_evidence_story_ref ON evidence_index(story_ref);
CREATE INDEX IF NOT EXISTS idx_evidence_page_url ON evidence_index(page_url);
CREATE INDEX IF NOT EXISTS idx_evidence_test_name ON evidence_index(test_name);
```

### 6.3 Module Design

New module: `src/evidence_index.py`

```python
class EvidenceIndex:
    """Indexes evidence sidecar metadata into SQLite for fast search/filter."""

    def __init__(self, db: SQLitePersistence | None = None) -> None:
        """Uses the existing SQLitePersistence singleton."""

    def build_or_refresh(
        self,
        base_dir: Path = Path("generated_tests"),
        force: bool = False,
    ) -> int:
        """Scan all evidence sidecars and upsert into evidence_index.
        Returns number of sidecars indexed.
        Uses file_mtime for incremental refresh — only re-reads changed files.
        """

    def search(
        self,
        query: str = "",
        status: str | None = None,
        url_domain: str | None = None,
        condition_prefix: str | None = None,
        story_ref: str | None = None,
        step_type: str | None = None,
        limit: int = 100,
    ) -> list[EvidenceSearchResult]:
        """Full-text search across evidence metadata."""

    def get_filter_options(self) -> EvidenceFilterOptions:
        """Return distinct values for filter dropdowns (statuses, domains, condition prefixes)."""

    def get_test_package_path(self, sidecar_path: str) -> Path:
        """Resolve a relative sidecar_path to an absolute Path."""


@dataclass
class EvidenceSearchResult:
    sidecar_path: str
    test_name: str
    condition_ref: str
    story_ref: str
    status: str
    page_url: str
    test_package: str
    matched_field: str       # which field matched the query


@dataclass
class EvidenceFilterOptions:
    statuses: list[str]              # distinct status values
    domains: list[str]               # distinct URL domains
    condition_prefixes: list[str]     # e.g. ["TC01", "TC02"]
    story_refs: list[str]
    step_types: list[str]
    total_indexed: int
    last_refreshed: str | None
```

### 6.4 Search Implementation

**Full-text search approach: SQL `LIKE` with multiple columns (no FTS5).**

Rationale: FTS5 adds complexity (separate virtual table, tokenizer configuration, rebuild on update) for a dataset that's small enough (hundreds of rows, tiny text) that `LIKE '%query%'` across indexed columns is fast and simple. If the dataset grows to thousands, we can upgrade to FTS5 later.

```sql
SELECT * FROM evidence_index
WHERE (
    test_name LIKE '%' || ? || '%'
    OR condition_ref LIKE '%' || ? || '%'
    OR story_ref LIKE '%' || ? || '%'
    OR page_url LIKE '%' || ? || '%'
    OR step_labels LIKE '%' || ? || '%'
)
AND (? IS NULL OR status = ?)
AND (? IS NULL OR page_url LIKE ? || '%')
AND (? IS NULL OR condition_ref LIKE ? || '%')
ORDER BY file_mtime DESC
LIMIT ?
```

The `matched_field` is determined post-query by checking which column matched (or set to `"multiple"`).

### 6.5 UI Design

Replace the flat `st.selectbox` in `EvidenceViewer._render_debug_export()` with:

```
┌─────────────────────────────────────────────────────────┐
│ 🔍 Search evidence...                    [🔄 Refresh]   │
├─────────────────────────────────────────────────────────┤
│ Status: [All ▾]  Domain: [All ▾]  Condition: [All ▾]   │
├─────────────────────────────────────────────────────────┤
│ Results (42 matching)                                   │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ❌ TC01.06 — test_cart_products...[chromium]        │ │
│ │    https://automationexercise.com/view_cart          │ │
│ │    Steps: navigate, assertion  |  Story: S06         │ │
│ ├─────────────────────────────────────────────────────┤ │
│ │ ✅ TC01.05 — test_view_cart...[chromium]            │ │
│ │    https://automationexercise.com/view_cart          │ │
│ │    Steps: navigate, assertion, assertion  |  S06     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Selected: ❌ TC01.06 — test_cart_products...            │
│ [annotated journey renders below]                       │
└─────────────────────────────────────────────────────────┘
```

Key UI changes:
- **Search bar** — text input with debounce, searches across all indexed fields
- **Filter row** — `st.multiselect` or `st.selectbox` for: status, domain, condition prefix
- **Results list** — replaces the flat selectbox; shows key metadata inline (URL, steps, story)
- **Refresh button** — triggers `EvidenceIndex.build_or_refresh()` to pick up new sidecars
- **Selection** — clicking a result renders the annotated journey below (existing behavior)

### 6.6 Index Build Strategy

**Lazy-first approach:** On first UI load, `EvidenceViewer.render()` calls `EvidenceIndex.build_or_refresh()` which:
1. Checks if `evidence_index` table exists and has rows
2. If empty → full scan (first run, ~1-2 seconds for hundreds of sidecars)
3. If populated → incremental: only re-read sidecars where `file_mtime` differs from stored value
4. Returns quickly if no changes detected

The index is persisted in SQLite, so it survives app restarts. The refresh button forces a full rebuild if needed.

---

## 7. Implementation Phases

### Phase 1: Evidence Index Module (no UI)
- [ ] `src/evidence_index.py` — `EvidenceIndex` class with `build_or_refresh()` and `search()`
- [ ] Schema migration in `src/sqlite_persistence.py` — add `evidence_index` table creation
- [ ] Unit tests: `tests/test_evidence_index.py` — mock sidecar JSON, test search queries, test incremental refresh
- [ ] Integration test: index real sidecars from `generated_tests/` and verify search results

### Phase 2: Export Formats (no UI)
- [ ] `src/evidence_export.py` — `export_csv()`, `export_ndjson()`, `export_junit_xml()` functions
- [ ] All exports accept the same filter parameters as `EvidenceIndex.search()` (query, status, domain, condition_prefix, story_ref)
- [ ] CSV: flat table with columns from §5.1
- [ ] NDJSON: one JSON object per line with full sidecar data
- [ ] JUnit XML: `<testsuites>` / `<testsuite>` / `<testcase>` structure, failure messages from step errors
- [ ] Unit tests: `tests/test_evidence_export.py` — validate CSV columns, NDJSON parseability, JUnit XML schema compliance
- [ ] Streamlit download buttons in evidence viewer (full dataset + filtered subset)

### Phase 3: Search Dataclasses + UI Integration
- [ ] `EvidenceSearchResult` and `EvidenceFilterOptions` dataclasses
- [ ] `EvidenceIndex.get_filter_options()` — returns distinct values for filter dropdowns
- [ ] `EvidenceIndex.search()` returns `list[EvidenceSearchResult]` with `matched_field`
- [ ] Replace `st.selectbox` in `_render_debug_export()` with search bar + filter row + results list
- [ ] Wire `EvidenceIndex` singleton into `EvidenceViewer`
- [ ] Add refresh button
- [ ] Add export download buttons (CSV, NDJSON, JUnit) next to search bar
- [ ] Preserve existing annotated journey rendering on selection
- [ ] Handle empty states gracefully ("No evidence matches your search")
- [ ] Unit tests for filter options and search result formatting

### Phase 4: CLI Integration
- [ ] `cli/evidence_cli.py` — unified CLI with `search` and `export` subcommands
- [ ] `python -m cli.evidence_cli search --query "dress" --status failed`
- [ ] `python -m cli.evidence_cli export --format csv --status failed --domain automationexercise.com --output evidence.csv`
- [ ] `python -m cli.evidence_cli export --format junit --output junit_report.xml`
- [ ] Table output for search, file output for export

---

## 8. Dependencies & Risks

| Dependency | Status |
|-----------|--------|
| AI-012 SQLite Persistence | Shipped — `SQLitePersistence` singleton used for index storage |
| AI-011 Run History Chart | Shipped — same `evidence/run_results.sqlite` file |

| Risk | Mitigation |
|------|-----------|
| Full scan on first load is slow with 500+ sidecars | Incremental refresh via `file_mtime`; benchmark with real data |
| Schema migration breaks existing SQLite DB | `CREATE TABLE IF NOT EXISTS` — additive only, no destructive migration |
| Search misses OCR text in screenshots | Non-goal; step labels provide text context |

---

## 9. Success Criteria

### Export (primary)
- [ ] CSV export opens in Excel with correct columns and no encoding issues
- [ ] NDJSON export is valid JSON Lines — `jq` and `pd.read_json(lines=True)` parse without error
- [ ] JUnit XML passes `xmllint --schema JUnit.xsd` validation
- [ ] All exports respect the same filters as search (status, domain, query, condition_prefix)
- [ ] CI/CD integration: JUnit XML consumed by GitHub Actions `dorny/test-reporter` without errors

### Search (convenience)
- [ ] User types "dress" → sees only evidence sidecars with "dress" in test name, step labels, or URL
- [ ] User filters by domain "automationexercise.com" → only that site's evidence shown
- [ ] User filters by status "failed" → only failed evidence shown
- [ ] Combined: "dress" + "automationexercise.com" + "failed" returns precise results

### Performance
- [ ] Index builds in <2 seconds on first load, <200ms on incremental refresh
- [ ] Search returns results in <50ms for 500 indexed sidecars

### Quality
- [ ] ruff clean, mypy clean, all existing tests pass
- [ ] 30+ new unit tests (`test_evidence_index.py` + `test_evidence_export.py`)

---

## 10. Open Questions

1. **Should the index auto-refresh on every UI load, or only on manual refresh?**  
   → Proposal: auto-refresh incrementally (mtime check, cheap), with a force-rebuild button for edge cases.

2. **Should we also index the test_plan condition descriptions (from `st.session_state.test_plan`) for richer search?**  
   → Worth considering in a follow-up — would allow searching by requirement text like "user should be able to add items to cart".

3. **Should we include screenshots in the export package (e.g. zip with PNGs)?**  
   → Defer. CSV/NDJSON/JUnit export the metadata. A full evidence bundle (sidecars + PNGs) is a separate concern already partially handled by the existing export service.

4. **Should Gantt (AI-021), run pass rate (AI-011), and heat map (AI-022) use `evidence_index` as their data source?**  
   → Follow-up session after AI-028 ships. Currently each feature scans `.evidence.json` sidecars independently. Retrofitting them to query `evidence_index` would: make Gantt filterable by story/date, enable pass rate JOINs between `test_results` and `evidence_index`, and replace heat map's full-file-scan with a single SQL aggregation. The index makes this cheap — the retrofits are wiring, not new infrastructure.

---

*Created: 2026-07-19*
