"""Tests for configurable is_business_hours() via env vars.

Covers:
- Default window (Mon-Fri 13:00-21:00 UTC) unchanged.
- Custom start/end hours via UTILITY_BUSINESS_HOURS_START_UTC / END_UTC.
- Custom day set via UTILITY_BUSINESS_HOURS_DAYS.
- APAC-style window (00:00-09:00 UTC, Mon-Fri as JST business hours proxy).
- Weekend-operating setup (days=0,1,2,3,4,5,6).
- Invalid env values fall back to defaults silently.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


# Helper — build datetime fast
def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=UTC)


# Monday 2026-04-20 (weekday=0), Wednesday 2026-04-22 (weekday=2), Saturday 2026-04-25 (weekday=5)
_MON_14 = _dt(2026, 4, 20, 14)  # Monday 14:00 UTC
_WED_14 = _dt(2026, 4, 22, 14)  # Wednesday 14:00 UTC
_SAT_14 = _dt(2026, 4, 25, 14)  # Saturday 14:00 UTC
_WED_04 = _dt(2026, 4, 22, 4)  # Wednesday 04:00 UTC (off-hours)
_WED_22 = _dt(2026, 4, 22, 22)  # Wednesday 22:00 UTC (past end)
_WED_13 = _dt(2026, 4, 22, 13)  # Wednesday 13:00 UTC (exactly at start)
_WED_21 = _dt(2026, 4, 22, 21)  # Wednesday 21:00 UTC (exactly at end — excluded)


# ── Default window ────────────────────────────────────────────────────────────


def test_default_weekday_in_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    assert is_business_hours(_WED_14) is True
    assert is_business_hours(_MON_14) is True


def test_default_weekend_is_off_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    assert is_business_hours(_SAT_14) is False


def test_default_early_morning_is_off_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    assert is_business_hours(_WED_04) is False


def test_default_boundary_start_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    assert is_business_hours(_WED_13) is True  # 13:00 is start, inclusive


def test_default_boundary_end_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    assert is_business_hours(_WED_21) is False  # 21:00 is end, exclusive
    assert is_business_hours(_WED_22) is False


# ── Custom start/end hours ────────────────────────────────────────────────────


def test_custom_start_end_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_START_UTC", "9")
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_END_UTC", "17")
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Wed 09:00 UTC — in window
    assert is_business_hours(_dt(2026, 4, 22, 9)) is True
    # Wed 16:00 UTC — in window
    assert is_business_hours(_dt(2026, 4, 22, 16)) is True
    # Wed 17:00 UTC — exclusive end
    assert is_business_hours(_dt(2026, 4, 22, 17)) is False
    # Wed 04:00 UTC — before start
    assert is_business_hours(_WED_04) is False


# ── APAC window ───────────────────────────────────────────────────────────────


def test_apac_window_utc_00_09(monkeypatch: pytest.MonkeyPatch) -> None:
    """Japanese business hours (09:00-18:00 JST) map to 00:00-09:00 UTC."""
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_START_UTC", "0")
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_END_UTC", "9")
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_DAYS", "0,1,2,3,4")
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Mon 01:00 UTC = Mon 10:00 JST — in window
    assert is_business_hours(_dt(2026, 4, 20, 1)) is True
    # Mon 08:59 UTC — still in window
    assert is_business_hours(_dt(2026, 4, 20, 8)) is True
    # Mon 09:00 UTC — exclusive end (18:00 JST)
    assert is_business_hours(_dt(2026, 4, 20, 9)) is False
    # Sat 01:00 UTC — weekend
    assert is_business_hours(_dt(2026, 4, 25, 1)) is False


# ── Weekend-operating setup ───────────────────────────────────────────────────


def test_seven_day_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_DAYS", "0,1,2,3,4,5,6")
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Saturday 14:00 UTC — now in the operating window
    assert is_business_hours(_SAT_14) is True
    # Sunday 14:00 UTC — 2026-04-26 is Sunday (weekday=6)
    assert is_business_hours(_dt(2026, 4, 26, 14)) is True
    # Saturday 04:00 UTC — outside default hours (before 13:00)
    assert is_business_hours(_dt(2026, 4, 25, 4)) is False


# ── Invalid env values fall back silently ────────────────────────────────────


def test_invalid_start_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_START_UTC", "not_a_number")
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_DAYS", raising=False)
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Should use default 13 — Wed 14 UTC is in window
    assert is_business_hours(_WED_14) is True


def test_invalid_days_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_DAYS", "bad,data,here")
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Default days = Mon-Fri; Saturday should be off
    assert is_business_hours(_SAT_14) is False


def test_out_of_range_days_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_START_UTC", raising=False)
    monkeypatch.delenv("UTILITY_BUSINESS_HOURS_END_UTC", raising=False)
    monkeypatch.setenv("UTILITY_BUSINESS_HOURS_DAYS", "0,1,7,8")  # 7,8 are invalid
    from utility_server.tools.renew_certificate.plan import is_business_hours

    # Falls back to Mon-Fri default; Saturday is off
    assert is_business_hours(_SAT_14) is False
