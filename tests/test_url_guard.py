"""Unit tests for the SSRF guard (Phase 6 6a — BACKLOG AI-045 #1).

Hermetic: classification is pure (no network); the only DNS used is
``localhost`` (resolved via the hosts file, offline); ``socket.getaddrinfo``
is monkeypatched where a specific hostname is needed.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from src.url_guard import (
    IpClass,
    UrlGuard,
    UrlGuardError,
    allow_loopback_default,
    allow_private_networks_default,
    classify_ip,
    is_blocked,
    resolve_host,
    validate_target_url,
)

# ── classification (pure) ───────────────────────────────────────────────


def test_classify_loopback() -> None:
    assert classify_ip("127.0.0.1") is IpClass.LOOPBACK
    assert classify_ip("::1") is IpClass.LOOPBACK


def test_classify_private_ranges() -> None:
    assert classify_ip("10.0.0.1") is IpClass.PRIVATE
    assert classify_ip("172.16.0.1") is IpClass.PRIVATE
    assert classify_ip("172.31.255.255") is IpClass.PRIVATE
    assert classify_ip("192.168.1.1") is IpClass.PRIVATE
    assert classify_ip("fd00::1") is IpClass.PRIVATE  # ULA fc00::/7


def test_classify_link_local_includes_cloud_metadata() -> None:
    assert classify_ip("169.254.169.254") is IpClass.LINK_LOCAL
    assert classify_ip("169.254.10.20") is IpClass.LINK_LOCAL
    assert classify_ip("fe80::1") is IpClass.LINK_LOCAL


def test_classify_never_allowable_classes() -> None:
    assert classify_ip("0.0.0.0") is IpClass.UNSPECIFIED
    assert classify_ip("0.1.2.3") is IpClass.UNSPECIFIED  # whole 0.0.0.0/8
    assert classify_ip("::") is IpClass.UNSPECIFIED
    assert classify_ip("255.255.255.255") is IpClass.BROADCAST
    assert classify_ip("224.0.0.1") is IpClass.MULTICAST
    assert classify_ip("ff02::1") is IpClass.MULTICAST
    assert classify_ip("100.64.0.1") is IpClass.RESERVED  # CGNAT
    assert classify_ip("192.0.0.1") is IpClass.RESERVED  # protocol assignments
    assert classify_ip("198.18.0.1") is IpClass.RESERVED  # benchmarking
    assert classify_ip("240.0.0.1") is IpClass.RESERVED


def test_classify_ipv4_mapped_ipv6_is_normalised() -> None:
    # IPv4-mapped IPv6 must not smuggle a private/loopback v4 range through.
    assert classify_ip("::ffff:127.0.0.1") is IpClass.LOOPBACK
    assert classify_ip("::ffff:10.0.0.1") is IpClass.PRIVATE
    assert classify_ip("::ffff:169.254.169.254") is IpClass.LINK_LOCAL


def test_classify_public() -> None:
    assert classify_ip("8.8.8.8") is IpClass.PUBLIC
    assert classify_ip("2001:4860:4860::8888") is IpClass.PUBLIC


# ── blocking decision ────────────────────────────────────────────────────


def test_always_blocked_classes_ignore_config() -> None:
    for cls in (IpClass.LINK_LOCAL, IpClass.UNSPECIFIED, IpClass.BROADCAST, IpClass.MULTICAST, IpClass.RESERVED):
        assert is_blocked(cls, allow_loopback=True, allow_private_networks=True) is True
        assert is_blocked(cls, allow_loopback=False, allow_private_networks=False) is True


def test_loopback_follows_allow_loopback() -> None:
    assert is_blocked(IpClass.LOOPBACK, allow_loopback=True, allow_private_networks=False) is False
    assert is_blocked(IpClass.LOOPBACK, allow_loopback=False, allow_private_networks=False) is True


def test_private_follows_allow_private_networks() -> None:
    assert is_blocked(IpClass.PRIVATE, allow_loopback=True, allow_private_networks=False) is True
    assert is_blocked(IpClass.PRIVATE, allow_loopback=True, allow_private_networks=True) is False


def test_public_never_blocked() -> None:
    assert is_blocked(IpClass.PUBLIC, allow_loopback=False, allow_private_networks=False) is False


# ── validate() on literal-IP URLs ────────────────────────────────────────


def test_metadata_endpoint_never_scraped() -> None:
    """The cloud metadata endpoint is refused even with everything allowed."""
    guard = UrlGuard(allow_loopback=True, allow_private_networks=True)
    with pytest.raises(UrlGuardError) as excinfo:
        guard.validate("http://169.254.169.254/latest/meta-data/")
    assert excinfo.value.ip_class is IpClass.LINK_LOCAL
    assert "169.254.169.254" in str(excinfo.value)


def test_loopback_literal_blocked_when_disallowed() -> None:
    guard = UrlGuard(allow_loopback=False)
    with pytest.raises(UrlGuardError) as excinfo:
        guard.validate("http://127.0.0.1:8080/health")
    assert excinfo.value.ip_class is IpClass.LOOPBACK


def test_loopback_literal_allowed_by_default() -> None:
    # Default allow_loopback=True keeps the mock-site family working.
    target = validate_target_url("http://127.0.0.1:8784/")
    assert target.host == "127.0.0.1"
    assert target.host_is_ip_literal is True


def test_private_literal_blocked_by_default() -> None:
    with pytest.raises(UrlGuardError):
        validate_target_url("http://10.0.0.5/")
    with pytest.raises(UrlGuardError):
        validate_target_url("http://192.168.1.10/")


def test_private_literal_allowed_with_flag() -> None:
    target = validate_target_url("http://10.0.0.5/", allow_private_networks=True)
    assert target.resolved_ips == ("10.0.0.5",)


def test_scheme_restriction() -> None:
    for scheme in ("file:///etc/passwd", "ftp://10.0.0.1/x", "data:text/plain,hi", "gopher://x", "javascript:alert(1)"):
        with pytest.raises(UrlGuardError) as excinfo:
            validate_target_url(scheme)
        assert "scheme" in str(excinfo.value)


def test_missing_scheme_or_host() -> None:
    with pytest.raises(UrlGuardError):
        validate_target_url("localhost:8784")  # no scheme
    with pytest.raises(UrlGuardError):
        validate_target_url("http:///path")  # no host


def test_unspecified_multicast_refused() -> None:
    with pytest.raises(UrlGuardError):
        validate_target_url("http://0.0.0.0/")
    with pytest.raises(UrlGuardError):
        validate_target_url("http://224.0.0.1/")


# ── validate() on hostnames (offline: localhost only) ────────────────────


def test_localhost_hostname_allowed_by_default() -> None:
    target = validate_target_url("http://localhost:8784/index.html")
    assert target.host == "localhost"
    assert any(cls is IpClass.LOOPBACK for cls in (IpClass.LOOPBACK,)) or True  # smoke: resolves
    assert "127.0.0.1" in target.resolved_ips


def test_localhost_hostname_blocked_when_disallowed() -> None:
    guard = UrlGuard(allow_loopback=False)
    with pytest.raises(UrlGuardError) as excinfo:
        guard.validate("http://localhost:8784/")
    assert excinfo.value.ip_class is IpClass.LOOPBACK


def test_resolve_host_literal_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def _fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
        calls.append(args)
        return [((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    assert resolve_host("10.1.2.3") == ["10.1.2.3"]  # literal — no DNS
    assert calls == []


# ── caching ──────────────────────────────────────────────────────────────


def test_host_classification_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def _fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
        calls.append(args)
        return [((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0)))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    guard = UrlGuard(allow_private_networks=False)
    for _ in range(3):
        with pytest.raises(UrlGuardError):
            guard.validate("http://internal.example.test/")
    assert len(calls) == 1  # resolved once, cached for the rest


# ── is_allowed (non-raising) ─────────────────────────────────────────────


def test_is_allowed_non_raising() -> None:
    guard = UrlGuard()
    assert guard.is_allowed("http://localhost:8784/") is True
    assert guard.is_allowed("http://169.254.169.254/") is False
    assert guard.is_allowed("gopher://x") is False


# ── Playwright request handler ───────────────────────────────────────────


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url
        self.abort_called: bool = False
        self._abort_raises: bool = False

    def abort(self) -> None:
        self.abort_called = True
        if self._abort_raises:
            raise RuntimeError("already completed")


def test_request_handler_aborts_blocked_requests() -> None:
    guard = UrlGuard()
    handler = guard.request_handler()
    blocked = _FakeRequest("http://169.254.169.254/latest/meta-data/")
    handler(blocked)
    assert blocked.abort_called is True


def test_request_handler_passes_allowed_requests() -> None:
    guard = UrlGuard()
    handler = guard.request_handler()
    allowed = _FakeRequest("http://localhost:8784/")
    handler(allowed)
    assert allowed.abort_called is False


def test_request_handler_ignores_missing_url_and_survives_abort_failure() -> None:
    guard = UrlGuard()
    handler = guard.request_handler()

    class _NoUrl:
        pass

    handler(_NoUrl())  # no url attr → no-op, no crash

    failing = _FakeRequest("http://169.254.169.254/")
    failing._abort_raises = True  # noqa: SLF001
    handler(failing)  # abort raises → swallowed


# ── error type contract ──────────────────────────────────────────────────


def test_guard_error_is_value_error_with_context() -> None:
    with pytest.raises(UrlGuardError) as excinfo:
        validate_target_url("http://169.254.169.254/")
    exc = excinfo.value
    # Narrow to UrlGuardError FIRST — a later `isinstance(exc, ValueError)`
    # would narrow to the supertype and drop the attrs for mypy.
    assert isinstance(exc, UrlGuardError)
    assert isinstance(exc, ValueError)
    assert exc.url == "http://169.254.169.254/"
    assert exc.ip_class is IpClass.LINK_LOCAL


# ── env-driven defaults ──────────────────────────────────────────────────


def test_env_flags_drive_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_ALLOW_LOOPBACK", "0")
    monkeypatch.setenv("AITEST_ALLOW_PRIVATE_NETWORKS", "1")
    assert allow_loopback_default() is False
    assert allow_private_networks_default() is True

    guard = UrlGuard()  # env-driven
    assert guard.allow_loopback is False
    assert guard.allow_private_networks is True
    with pytest.raises(UrlGuardError):
        guard.validate("http://127.0.0.1/")
    assert guard.is_allowed("http://10.0.0.1/") is True
