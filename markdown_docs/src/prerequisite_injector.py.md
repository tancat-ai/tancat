# `src/prerequisite_injector.py`

## High-Level Purpose
Injects prerequisite setup code (fixtures, page navigation, auth state) into generated test functions before test body execution.

## Module Metadata
- **Lines:** ~180
- **Imports:** `re`, `dataclasses`, `typing`

## Classes

### `Prerequisite` (dataclass)
Single prerequisite block: type (goto, login, setup), code snippet, insert position.

## Functions

### `inject_prerequisites(code: str, prerequisites: list[Prerequisite]) -> str`
Injects prerequisite code blocks before test function body.

### `infer_prerequisites(story: UserStory) -> list[Prerequisite]`
Infers required prerequisites from user story (e.g., login before checkout).

### `_format_goto(url: str) -> str`
Generates `page.goto(url)` prerequisite line.

### `_format_login(credentials: dict) -> str`
Generates login prerequisite block.

## Key Design Decisions
- Prerequisite inference from story context, not manual config
- Insertion before first test assertion to preserve setup order
- No modification of test function signature

## Dependencies
- None from `src/` — stdlib only

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 3 items):

### `PrerequisiteStep` (class)

A resolved step extracted from a prerequisite test.

### `InjectionPlan` (class)

Describes what needs to be injected into a test.

### `PrerequisiteInjector` (class)

Detect dependency chains and inject prerequisite steps.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PrerequisiteInjector.__init__` (method of `PrerequisiteInjector`): `PrerequisiteInjector.__init__() -> None`
- `PrerequisiteInjector.analyze_dependencies` (method of `PrerequisiteInjector`): `PrerequisiteInjector.analyze_dependencies(journeys: list[TestJourney], starting_url: str, scraped_pages: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, InjectionPlan]` - Return injection plans for tests that need prerequisite steps. Args: journeys: Parsed test journeys from the skeleton parser. starting_url: The seed URL (usually the login/home page). scraped_pages: Optional scraped p...
- `PrerequisiteInjector.inject_into_code` (method of `PrerequisiteInjector`): `PrerequisiteInjector.inject_into_code(code: str, injection_plans: dict[str, InjectionPlan]) -> str` - Prepend prerequisite steps into the target test functions. Args: code: The resolved test code (after placeholder resolution). injection_plans: Mapping of test_name -> InjectionPlan from analyze_dependencies(). Returns:...
- `POST_AUTH_KEYWORDS` (constant): `POST_AUTH_KEYWORDS = {'cart', 'add to cart', 'add item', 'item', 'basket', 'sh...`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (9 items). Grouped under the public function that calls them.

### `PrerequisiteInjector.analyze_dependencies(journeys: list[TestJourney], starting_url: str, scraped_pages: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, InjectionPlan]` - method of `PrerequisiteInjector`

- `_extract_first_navigation(journey: TestJourney) -> tuple[str | None, str]` (method of `PrerequisiteInjector`): Extract the first GOTO target URL and criterion text from a journey.
- `_find_auth_test(journeys: list[TestJourney], starting_url: str) -> str | None` (method of `PrerequisiteInjector`): Find the test that performs authentication (login). Heuristic: the first test whose steps include FILL actions for credentials (username, password) or CLICK actions for login.
- `_needs_prerequisite_injection(journey: TestJourney, first_goto_url: str | None, criterion_text: str, starting_url: str, auth_test_name: str) -> bool` (method of `PrerequisiteInjector`): Determine if a test needs prerequisite injection. A test needs injection when: 1. Its first navigation targets the starting URL (login page), AND 2. The criterion describes a post-authentication action
- `_extract_prerequisite_steps(journey: TestJourney, condition_ref: str = '') -> list[PrerequisiteStep]` (method of `PrerequisiteInjector`): Extract resolved evidence_tracker ACTION steps from a journey. Only extracts action steps (navigate, click, fill) - NOT assertions. Assertions from a prerequisite test are meaningless when injected into a different te...

### `PrerequisiteInjector.inject_into_code(code: str, injection_plans: dict[str, InjectionPlan]) -> str` - method of `PrerequisiteInjector`

- `_detect_body_indent(lines: list[str], def_line_index: int) -> str` (method of `PrerequisiteInjector`): Detect the indentation of the function body.
- `_extract_tc_ref(reason: str) -> str` (method of `PrerequisiteInjector`): Extract TC reference from the injection reason string.

### Internal utilities

- `_journey_contains_auth_steps(journey: TestJourney) -> bool` (method of `PrerequisiteInjector`): Return True when the test already performs a login-like sequence.
- `_is_assertion_step(raw_line: str) -> bool` (method of `PrerequisiteInjector`): Return True if the line is an assertion (should not be injected).
- `_collect_decorators(lines: list[str], def_line_index: int) -> list[str]` (method of `PrerequisiteInjector`): Collect decorator lines preceding a function definition.
