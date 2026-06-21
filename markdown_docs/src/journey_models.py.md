# `src/journey_models.py`

## High-Level Purpose

`journey_models.py` defines lightweight data models for journey-aware scraping. The module is intentionally limited to pure dataclasses and a small template-substitution helper so callers can import journey data structures without also loading Playwright, subprocess, UI, or pipeline execution dependencies.

The models describe:

- Planned journey actions, such as navigation, clicks, fills, waits, and scraping.
- Scraped output captured at a specific journey step.
- In-memory credential profiles used for authenticated journeys.
- Aggregate journey execution results that can be serialized to and from JSON-friendly dictionaries.

## Imports and Dependencies

- `from __future__ import annotations`
  - Allows forward references such as `JourneyResult` in type annotations.
- `dataclasses.asdict`
  - Used to serialize nested dataclass-compatible values in `JourneyResult.to_dict()`.
- `dataclasses.dataclass`
  - Used for all public model classes.
- `dataclasses.field`
  - Used for the `JourneyResult.redirected_urls` mutable default list.
- `typing.Any`
  - Used for loosely typed scraped element dictionaries and JSON-like output.

The module has no runtime dependency on Playwright, Streamlit, subprocess execution, filesystem access, or network access.

## Classes

### `JourneyStep`

```python
@dataclass
class JourneyStep:
    action: str
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    description: str = ""
    timeout_ms: int = 30_000
```

Generated constructor signature:

```python
JourneyStep(
    action: str,
    url: str | None = None,
    selector: str | None = None,
    text: str | None = None,
    description: str = "",
    timeout_ms: int = 30000,
) -> None
```

Represents one action in a journey-aware scraping flow.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `action` | `str` | required | Action type, expected to represent values such as `"navigate"`, `"click"`, `"fill"`, `"wait"`, or `"scrape"`. |
| `url` | `str | None` | `None` | URL used by navigation steps. |
| `selector` | `str | None` | `None` | Element selector used by interaction steps such as click or fill. |
| `text` | `str | None` | `None` | Text entered during fill steps. |
| `description` | `str` | `""` | Human-readable step description. |
| `timeout_ms` | `int` | `30_000` | Per-step timeout in milliseconds. |

Methods:

- No custom methods are defined.
- Standard dataclass methods such as `__init__`, `__repr__`, and equality comparison are generated automatically.

### `ScrapedStep`

```python
@dataclass
class ScrapedStep:
    url: str
    elements: list[dict[str, Any]]
    step_index: int
    step_description: str = ""
```

Generated constructor signature:

```python
ScrapedStep(
    url: str,
    elements: list[dict[str, Any]],
    step_index: int,
    step_description: str = "",
) -> None
```

Represents the scraped result associated with a specific step in a journey.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `url` | `str` | required | URL that was scraped. |
| `elements` | `list[dict[str, Any]]` | required | Scraped element records for the URL. The element schema is intentionally flexible. |
| `step_index` | `int` | required | Index of the journey step that produced the scrape. |
| `step_description` | `str` | `""` | Human-readable description of the journey step. |

Methods:

- No custom methods are defined.
- Standard dataclass methods are generated automatically.

### `CredentialProfile`

```python
@dataclass
class CredentialProfile:
    label: str
    username: str
    password: str
```

Generated constructor signature:

```python
CredentialProfile(
    label: str,
    username: str,
    password: str,
) -> None
```

Represents user-provided credentials for authenticated journey scraping.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `label` | `str` | required | Human-readable name for the credential profile. |
| `username` | `str` | required | Username value used during templated fill steps. |
| `password` | `str` | required | Password value used during templated fill steps. |

Operational note:

- The source docstring states that credentials are stored in session state only and are never persisted to disk.

Methods:

- No custom methods are defined.
- Standard dataclass methods are generated automatically.

### `JourneyResult`

```python
@dataclass
class JourneyResult:
    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]
    failed_steps: list[str]
    error_message: str | None = None
    redirected_urls: list[str] = field(default_factory=list)
```

Generated constructor signature:

```python
JourneyResult(
    success: bool,
    captured_pages: dict[str, list[dict[str, Any]]],
    failed_steps: list[str],
    error_message: str | None = None,
    redirected_urls: list[str] = <new empty list>,
) -> None
```

Represents the aggregate outcome of executing a journey through authenticated or multi-step pages.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `success` | `bool` | required | Indicates whether the journey completed successfully. |
| `captured_pages` | `dict[str, list[dict[str, Any]]]` | required | Mapping from URL to scraped element records. |
| `failed_steps` | `list[str]` | required | Human-readable descriptions of failed journey steps. |
| `error_message` | `str | None` | `None` | Top-level journey error, such as SSO, MFA, or CAPTCHA failure. |
| `redirected_urls` | `list[str]` | new empty list | URLs reached through redirects during the journey. |

#### `JourneyResult.to_dict`

```python
def to_dict(self) -> dict[str, Any]:
```

Serializes the dataclass instance to a plain dictionary.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `self` | `JourneyResult` | Instance being serialized. |

Returns:

| Type | Description |
| --- | --- |
| `dict[str, Any]` | JSON-friendly dictionary produced by `dataclasses.asdict(self)`. |

Behavior:

- Converts the dataclass and contained dataclass-compatible structures into dictionaries and plain containers.
- Does not perform custom filtering, validation, or redaction.

#### `JourneyResult.from_dict`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> JourneyResult:
```

Deserializes a dictionary into a `JourneyResult`.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `cls` | `type[JourneyResult]` | Dataclass constructor target supplied by `@classmethod`. |
| `data` | `dict[str, Any]` | Dictionary containing serialized journey result fields. |

Returns:

| Type | Description |
| --- | --- |
| `JourneyResult` | New result instance built from the dictionary. |

Field mapping:

| Output Field | Source Expression | Fallback |
| --- | --- | --- |
| `success` | `bool(data.get("success", False))` | `False` |
| `captured_pages` | `data.get("captured_pages", {})` | `{}` |
| `failed_steps` | `data.get("failed_steps", [])` | `[]` |
| `error_message` | `data.get("error_message")` | `None` |
| `redirected_urls` | `data.get("redirected_urls", [])` | `[]` |

Behavior:

- Performs permissive dictionary loading with defaults for missing keys.
- Coerces `success` with `bool(...)`.
- Does not validate nested scraped element schemas.
- Does not copy or deep-copy dictionary values beyond the constructor assignment.

## Functions

### `substitute_templates`

```python
def substitute_templates(
    text: str,
    credential_profile: CredentialProfile | None,
) -> str:
```

Replaces supported credential placeholders in a text value.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `text` | `str` | Input text that may contain credential placeholders. |
| `credential_profile` | `CredentialProfile | None` | Credentials used for replacement. If `None`, no substitution occurs. |

Returns:

| Type | Description |
| --- | --- |
| `str` | The original text when no profile is provided, otherwise a new string with supported placeholders replaced. |

Supported placeholders:

| Placeholder | Replacement |
| --- | --- |
| `{{username}}` | `credential_profile.username` |
| `{{password}}` | `credential_profile.password` |

Behavior:

- Returns `text` unchanged when `credential_profile is None`.
- Replaces username first, then password.
- Does not mutate the credential profile.
- Does not support arbitrary template variables, escaping, conditional logic, or validation of unresolved placeholders.

## Architectural Patterns

### Lightweight Model Boundary

The module isolates journey data structures from execution code. This keeps model imports inexpensive and allows CLI, UI, tests, and orchestration code to share the same representations without importing browser automation machinery.

### Dataclass-Centric Data Transfer

All public classes are dataclasses. They function as simple data transfer objects with generated constructors, representations, and equality behavior rather than encapsulating browser or pipeline behavior.

### Flexible Scraped Element Schema

Scraped element collections use `list[dict[str, Any]]`. This preserves flexibility for DOM-derived records whose exact fields may vary across pages, scraping strategies, or downstream consumers.

### JSON-Friendly Serialization

`JourneyResult.to_dict()` and `JourneyResult.from_dict()` provide a small serialization boundary for storing or passing journey results as plain dictionaries. The implementation favors permissive defaults over strict validation.

### Safe Mutable Defaults

`JourneyResult.redirected_urls` uses `field(default_factory=list)` to avoid sharing one mutable list across instances.

### Explicit Credential Templating

`substitute_templates()` implements a narrow, predictable placeholder mechanism for credential injection. It intentionally only handles the two recognized placeholders, `{{username}}` and `{{password}}`.

## Side Effects

- Importing this module has no side effects beyond defining classes and functions.
- The module does not read or write files.
- The module does not access network resources.
- The module does not launch browsers or subprocesses.

