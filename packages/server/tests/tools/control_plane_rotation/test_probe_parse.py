"""Tests for openssl enddate parsing in probe.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from utility_server.tools.control_plane_rotation.probe import (
    _CERT_FILES,
    _TRANSIENT_MARKERS,
    parse_openssl_enddate,
)


@pytest.mark.parametrize(
    "line,expected",
    [
        # Double-space (day < 10, e.g. "5" pads to " 5")
        (
            "notAfter=Nov  5 12:34:56 2026 GMT",
            datetime(2026, 11, 5, 12, 34, 56, tzinfo=UTC),
        ),
        # Single-space (day >= 10)
        (
            "notAfter=Nov 15 12:34:56 2026 GMT",
            datetime(2026, 11, 15, 12, 34, 56, tzinfo=UTC),
        ),
        # Exactly what openssl outputs for Jan 1
        (
            "notAfter=Jan  1 00:00:00 2027 GMT",
            datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC),
        ),
        # Dec 31
        (
            "notAfter=Dec 31 23:59:59 2026 GMT",
            datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        ),
        # Without "notAfter=" prefix (bare date_str should fail gracefully)
        ("no equals sign here", None),
        # Empty string
        ("", None),
        # Garbage after equals
        ("notAfter=garbage data xyz", None),
    ],
)
def test_parse_openssl_enddate(line: str, expected: datetime | None) -> None:
    result = parse_openssl_enddate(line)
    assert result == expected


# ── Gap 1 fix: chroot /host wrapping ──────────────────────────────────────────


def test_cert_files_use_host_root_paths() -> None:
    """_CERT_FILES paths must be relative to host root (used via chroot /host), not /host/..."""
    for key, path in _CERT_FILES.items():
        assert not path.startswith("/host/"), (
            f"_CERT_FILES[{key!r}] = {path!r} still uses /host/ prefix; "
            "should be /etc/kubernetes/... (chroot handles /host)"
        )
        assert path.startswith("/etc/kubernetes/"), (
            f"_CERT_FILES[{key!r}] = {path!r} unexpected path"
        )


def test_probe_openssl_cmd_starts_with_chroot() -> None:
    """Probe command list for openssl must start with ['chroot', '/host', 'openssl', ...]."""
    # Build the command list the same way probe_node_certs does:
    path = _CERT_FILES["apiserver"]
    cmd = ["chroot", "/host", "openssl", "x509", "-enddate", "-noout", "-in", path]
    assert cmd[0] == "chroot"
    assert cmd[1] == "/host"
    assert cmd[2] == "openssl"
    assert "-enddate" in cmd
    # Path must NOT contain /host/ prefix (would be double-chroot)
    assert not any("/host/etc" in arg for arg in cmd), (
        "Command contains /host/etc which means double-chroot path"
    )


# ── Gap 2 fix: transient markers ────────────────────────────────────────────


def test_transient_markers_contains_expected_strings() -> None:
    """_TRANSIENT_MARKERS must include the errors seen during kubelet cert reload."""
    required = [
        "use of closed network connection",
        "connection refused",
        "unexpected EOF",
        "error dialing backend",
        "TLS handshake timeout",
    ]
    for marker in required:
        assert marker in _TRANSIENT_MARKERS, (
            f"_TRANSIENT_MARKERS missing {marker!r} — retry logic won't catch this error"
        )
