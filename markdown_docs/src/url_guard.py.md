# `src/url_guard.py`

## Purpose

SSRF guard for scraped target URLs (Phase 6 6a - BACKLOG AI-045 #1). Blocks navigation/scraping of private, link-local (including the cloud metadata endpoint 169.254.169.254), loopback (configurable), and non-http...

## Module Metadata

- **Lines:** ~351
- **Imports:** `__future__.annotations`, `collections.abc.Callable`, `dataclasses.dataclass`, `enum.Enum`, `ipaddress`, `logging`, `os`, `socket`, `typing.Any`, `urllib.parse.urlparse`

## Classes

| Class | Description |
|-------|-------------|
| `IpClass` | Classification of a resolved IP address. |
| `UrlGuardError` | Raised when a target URL is refused by the SSRF guard. Subclasses ValueError so callers that already treat bad URLs as config/runtime errors (the pipelin... |
| `SafeTarget` | A URL that passed the guard, with its resolved addresses. resolved_ips powers first-hop pinning: callers that want to close the check-then-connect race m... |
| `UrlGuard` | Resolve-and-classify SSRF guard with a small per-host cache. Safe for use in Playwright subprocesses (pure stdlib, no network at import; DNS only happens ins... |

## Functions

| Function | Description |
|----------|-------------|
| `allow_loopback_default() -> bool` | Env-driven default: loopback targets permitted (mock family, local dev). |
| `allow_private_networks_default() -> bool` | Env-driven default: RFC1918/ULA targets refused unless explicitly enabled. |
| `classify_ip(ip_str: str) -> IpClass` | Classify a single IP literal string into an IpClass. IPv4-mapped IPv6 (::ffff:a.b.c.d) is normalised to the embedded IPv4 address before classificati... |
| `is_blocked(ip_class: IpClass, *, allow_loopback: bool, allow_private_networks: bool) -> bool` | Decide whether an address class is refused under the given config. |
| `resolve_host(host: str) -> list[str]` | Return every IP literal *host* resolves to (or [host] when a literal). Raises socket.gaierror when the hostname does not resolve. |
| `UrlGuard.validate(url: str) -> SafeTarget` | Validate *url*; raise UrlGuardError when refused. |
| `UrlGuard.is_allowed(url: str) -> bool` | Non-raising form of :meth:'validate'. |
| `UrlGuard.request_handler() -> Callable[[Any], None]` | Return a Playwright page.on("request") handler. The handler re-checks every request URL (main navigations, redirects, and sub-resources) and aborts refus... |
| `validate_target_url(url: str, *, allow_loopback: bool | None = None, allow_private_networks: bool | None = None) -> SafeTarget` | One-shot convenience wrapper around :class:'UrlGuard'. |

## How It Works (Internals)

Private `_`-helpers - the module's real logic (4 items). Grouped under the public function that calls them.

### `allow_loopback_default() -> bool` - function

- `_env_flag(name: str, default: bool) -> bool` (function): Env flag; returns bool.

### `resolve_host(host: str) -> list[str]` - function

- `_is_ip_literal(host: str) -> bool` (function): Is ip literal; calls `ip_address`; returns bool.

### `UrlGuard.validate(url: str) -> SafeTarget` - method of `UrlGuard`

- `_classify_host(host: str) -> tuple[list[IpClass], list[str]]` (method of `UrlGuard`): Classify host; calls `classify_ip`, `resolve_host`; returns tuple[list[IpClass], list[str]].
- `_blocked_message(url: str, host: str, ip_class: IpClass) -> str` (method of `UrlGuard`): Blocked message; returns str.
