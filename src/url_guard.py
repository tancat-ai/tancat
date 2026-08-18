"""SSRF guard for scraped target URLs (Phase 6 6a — BACKLOG AI-045 #1).

Blocks navigation/scraping of private, link-local (including the cloud
metadata endpoint ``169.254.169.254``), loopback (configurable), and
non-http(s) URLs so that an LLM-hallucinated or attacker-supplied URL can
never turn the browser-based scraper into a proxy into the deployment's
internal network.

Design (see docs/specs/FEATURE_SPEC_phase6_saas.md §5.1):

- Resolve-and-classify per host with a small in-memory cache; every IP a
  hostname resolves to is classified and the worst class decides.
- Three enforcement layers:
  * scheme restriction — http/https only;
  * ALWAYS-BLOCK — link-local (169.254/16 incl. cloud metadata, fe80::/10),
    unspecified (0.0.0.0/8, ::/128), broadcast (255.255.255.255),
    multicast (224.0.0.0/4, ff00::/8), IETF-reserved — never configurable;
  * LOOPBACK (127.0.0.0/8, ::1) — blocked when ``allow_loopback=False``
    (default ON: the product's own mock-site family and local dev servers
    live on loopback, and loopback traffic never leaves the deployment);
  * PRIVATE (10/8, 172.16/12, 192.168/16, fc00::/7 ULA) — blocked when
    ``allow_private_networks=False`` (default) for internal staging.
- ``UrlGuard.request_handler()`` returns a Playwright ``page.on("request")``
  handler so redirects and sub-resources are re-checked at request time
  (closes the DNS-rebinding race within a scrape session).
- LLM endpoints are intentionally NOT guarded here — a BYO-LLM deployment
  legitimately points at ``http://localhost:11434`` (decision D1). This
  guard applies to *scraped target URLs* only.

Config env vars (mirror the existing ``AITEST_*`` convention):

- ``AITEST_ALLOW_LOOPBACK`` (default ``1``) — permit loopback targets.
- ``AITEST_ALLOW_PRIVATE_NETWORKS`` (default ``0``) — permit RFC1918/ULA
  targets (internal staging networks). Surfaced as a prominent warning by
  callers.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class IpClass(Enum):
    """Classification of a resolved IP address."""

    PUBLIC = "public"
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    PRIVATE = "private"
    UNSPECIFIED = "unspecified"
    BROADCAST = "broadcast"
    MULTICAST = "multicast"
    RESERVED = "reserved"


class UrlGuardError(ValueError):
    """Raised when a target URL is refused by the SSRF guard.

    Subclasses ``ValueError`` so callers that already treat bad URLs as
    config/runtime errors (the pipeline, ``scripts/ci_generate.py``) handle
    it without new machinery.
    """

    def __init__(self, message: str, *, url: str, ip_class: IpClass | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.ip_class = ip_class


# Address classes that are refused regardless of configuration.
_ALWAYS_BLOCKED: frozenset[IpClass] = frozenset(
    {
        IpClass.LINK_LOCAL,
        IpClass.UNSPECIFIED,
        IpClass.BROADCAST,
        IpClass.MULTICAST,
        IpClass.RESERVED,
    }
)


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def allow_loopback_default() -> bool:
    """Env-driven default: loopback targets permitted (mock family, local dev)."""
    return _env_flag("AITEST_ALLOW_LOOPBACK", True)


def allow_private_networks_default() -> bool:
    """Env-driven default: RFC1918/ULA targets refused unless explicitly enabled."""
    return _env_flag("AITEST_ALLOW_PRIVATE_NETWORKS", False)


def classify_ip(ip_str: str) -> IpClass:
    """Classify a single IP literal string into an ``IpClass``.

    IPv4-mapped IPv6 (``::ffff:a.b.c.d``) is normalised to the embedded IPv4
    address before classification so it cannot smuggle a private v4 range
    through an IPv6-shaped address.

    ``PRIVATE`` is defined explicitly as RFC1918 + IPv6 ULA rather than via
    ``ip.is_private``, because Python 3.13+ marks the entire IANA
    special-purpose registry as private (0.0.0.0/8, 100.64/10, 192.0.0.0/24,
    198.18/15, 240/4, …) — those ranges have no legitimate use as test
    targets and must stay in the unconditionally-blocked classes.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not parseable as an IP literal — treat as public; callers only
        # pass literals here (hostname resolution returns literals).
        return IpClass.PUBLIC
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return IpClass.LOOPBACK
    if ip.is_link_local:
        return IpClass.LINK_LOCAL
    if ip.is_multicast:
        return IpClass.MULTICAST
    if ip.is_unspecified:
        return IpClass.UNSPECIFIED
    if ip.version == 4:
        value = int(ip)
        if value >> 24 == 0:  # 0.0.0.0/8 "this network"
            return IpClass.UNSPECIFIED
        if value == 0xFFFFFFFF:  # limited broadcast
            return IpClass.BROADCAST
        # Shared-address-space / protocol-assignment / benchmarking ranges —
        # no legitimate test-target use, always blocked.
        if _ipv4_in(value, "100.64.0.0/10") or _ipv4_in(value, "192.0.0.0/24") or _ipv4_in(value, "198.18.0.0/15"):
            return IpClass.RESERVED
    for net in _RFC1918_AND_ULA:
        if ip in net:
            return IpClass.PRIVATE
    if ip.is_reserved:
        return IpClass.RESERVED
    return IpClass.PUBLIC


_RFC1918_AND_ULA: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
)


def _ipv4_in(value: int, cidr: str) -> bool:
    return ipaddress.ip_address(value) in ipaddress.ip_network(cidr)


def is_blocked(ip_class: IpClass, *, allow_loopback: bool, allow_private_networks: bool) -> bool:
    """Decide whether an address class is refused under the given config."""
    if ip_class in _ALWAYS_BLOCKED:
        return True
    if ip_class is IpClass.LOOPBACK:
        return not allow_loopback
    if ip_class is IpClass.PRIVATE:
        return not allow_private_networks
    return False


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host(host: str) -> list[str]:
    """Return every IP literal *host* resolves to (or ``[host]`` when a literal).

    Raises ``socket.gaierror`` when the hostname does not resolve.
    """
    if _is_ip_literal(host):
        return [host]
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips: list[str] = []
    for info in infos:
        # getaddrinfo's sockaddr tuple is loosely typed (str | int); the host
        # field is always the IP literal as text.
        addr = str(info[4][0])
        if addr not in ips:
            ips.append(addr)
    return ips


@dataclass(frozen=True)
class SafeTarget:
    """A URL that passed the guard, with its resolved addresses.

    ``resolved_ips`` powers first-hop pinning: callers that want to close the
    check-then-connect race may navigate to the resolved IP directly.
    """

    url: str
    host: str
    port: int | None
    resolved_ips: tuple[str, ...]
    host_is_ip_literal: bool


class UrlGuard:
    """Resolve-and-classify SSRF guard with a small per-host cache.

    Safe for use in Playwright subprocesses (pure stdlib, no network at
    import; DNS only happens inside ``validate``/``is_allowed``).
    """

    def __init__(
        self,
        *,
        allow_loopback: bool | None = None,
        allow_private_networks: bool | None = None,
        max_cache: int = 256,
    ) -> None:
        self.allow_loopback = allow_loopback_default() if allow_loopback is None else allow_loopback
        self.allow_private_networks = (
            allow_private_networks_default() if allow_private_networks is None else allow_private_networks
        )
        self._max_cache = max_cache
        # host -> (classes, ips)
        self._cache: dict[str, tuple[list[IpClass], list[str]]] = {}

    def _classify_host(self, host: str) -> tuple[list[IpClass], list[str]]:
        cached = self._cache.get(host)
        if cached is not None:
            return cached
        ips = resolve_host(host)
        classes = [classify_ip(ip) for ip in ips] or [IpClass.PUBLIC]
        result = (classes, ips)
        if len(self._cache) < self._max_cache:
            self._cache[host] = result
        return result

    def _blocked_message(self, url: str, host: str, ip_class: IpClass) -> str:
        if ip_class is IpClass.LOOPBACK:
            hint = (
                "loopback addresses are blocked; set AITEST_ALLOW_LOOPBACK=1 to permit local targets"
                if not self.allow_loopback
                else ""
            )
        elif ip_class is IpClass.PRIVATE:
            hint = (
                "private/internal networks are blocked by default; set "
                "AITEST_ALLOW_PRIVATE_NETWORKS=1 to permit them (internal staging only)"
                if not self.allow_private_networks
                else ""
            )
        else:
            hint = "this address class is always blocked by the SSRF guard"
        return f"SSRF guard refused '{url}': host '{host}' resolves to a {ip_class.value} address ({hint})".strip()

    def validate(self, url: str) -> SafeTarget:
        """Validate *url*; raise ``UrlGuardError`` when refused."""
        try:
            parsed = urlparse(url)
        except ValueError as exc:
            raise UrlGuardError(f"SSRF guard refused '{url}': malformed URL ({exc})", url=url) from exc

        if parsed.scheme not in ("http", "https"):
            raise UrlGuardError(
                f"SSRF guard refused '{url}': scheme '{parsed.scheme or '<none>'}' is not http/https",
                url=url,
            )
        host = parsed.hostname
        if not host:
            raise UrlGuardError(f"SSRF guard refused '{url}': no host in URL", url=url)

        classes, ips = self._classify_host(host)
        for ip_class in classes:
            if is_blocked(
                ip_class, allow_loopback=self.allow_loopback, allow_private_networks=self.allow_private_networks
            ):
                raise UrlGuardError(
                    self._blocked_message(url, host, ip_class),
                    url=url,
                    ip_class=ip_class,
                )
        return SafeTarget(
            url=url,
            host=host,
            port=parsed.port,
            resolved_ips=tuple(ips),
            host_is_ip_literal=_is_ip_literal(host),
        )

    def is_allowed(self, url: str) -> bool:
        """Non-raising form of :meth:`validate`."""
        try:
            self.validate(url)
            return True
        except UrlGuardError:
            return False

    def request_handler(self) -> Callable[[Any], None]:
        """Return a Playwright ``page.on("request")`` handler.

        The handler re-checks every request URL (main navigations, redirects,
        and sub-resources) and aborts refused ones. Redirects are covered
        because Playwright emits a request event per hop; the per-host cache
        keeps repeated same-origin requests cheap.
        """

        def _handler(request: Any) -> None:
            url = getattr(request, "url", None)
            if not url:
                return
            try:
                self.validate(url)
            except UrlGuardError as exc:
                logger.warning("SSRF guard aborted request %s: %s", url, exc)
                abort = getattr(request, "abort", None)
                if abort is not None:
                    try:
                        abort()
                    except Exception:  # request may have completed already
                        pass

        return _handler


def validate_target_url(
    url: str,
    *,
    allow_loopback: bool | None = None,
    allow_private_networks: bool | None = None,
) -> SafeTarget:
    """One-shot convenience wrapper around :class:`UrlGuard`."""
    return UrlGuard(
        allow_loopback=allow_loopback,
        allow_private_networks=allow_private_networks,
    ).validate(url)
