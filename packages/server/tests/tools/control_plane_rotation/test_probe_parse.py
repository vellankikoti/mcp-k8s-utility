"""Tests for openssl enddate parsing in probe.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from utility_server.tools.control_plane_rotation.probe import (
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
