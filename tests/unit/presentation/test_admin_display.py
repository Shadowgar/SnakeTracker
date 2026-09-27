from __future__ import annotations

from datetime import UTC, datetime, timedelta

from snaketracker.presentation.admin_display import (
    admin_datetime,
    admin_quantity,
    admin_session_status,
    admin_short_id,
    admin_user_agent,
)


def test_admin_dates_use_household_timezone_and_keep_invalid_data_explicit() -> None:
    value = "2026-09-26T06:49:51.953245+00:00"
    assert admin_datetime(value, "America/New_York") == "Sep 26, 2026 · 2:49 AM EDT"
    assert admin_datetime(value, "UTC") == "Sep 26, 2026 · 6:49 AM UTC"
    assert admin_datetime(None) == "Not recorded"
    assert admin_datetime("invalid") == "Not recorded"


def test_session_status_prioritizes_revocation_and_both_expiries() -> None:
    now = datetime(2026, 9, 27, tzinfo=UTC)
    active = {
        "revoked_at": None,
        "idle_expires_at": (now + timedelta(minutes=20)).isoformat(),
        "absolute_expires_at": (now + timedelta(hours=1)).isoformat(),
    }
    assert admin_session_status(active, now=now) == "Active"
    assert admin_session_status({**active, "revoked_at": now.isoformat()}, now=now) == "Revoked"
    assert (
        admin_session_status(
            {**active, "idle_expires_at": (now - timedelta(seconds=1)).isoformat()}, now=now
        )
        == "Expired"
    )
    assert (
        admin_session_status(
            {**active, "absolute_expires_at": (now - timedelta(seconds=1)).isoformat()}, now=now
        )
        == "Expired"
    )


def test_user_agent_summary_and_full_id_presentation() -> None:
    assert admin_user_agent("Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/120 Mobile") == (
        "Chrome Mobile · Android"
    )
    assert admin_user_agent("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Edg/120") == (
        "Edge · Windows"
    )
    assert admin_user_agent("Mozilla/5.0 (iPhone) AppleWebKit Safari/604") == "Safari · iOS"
    assert admin_user_agent(None) == "Not recorded"
    assert admin_short_id("839eaf4a-3cde-5e1b-a9ef-11f4df9cdfb4") == "839eaf4a…cdfb4"


def test_admin_quantity_uses_existing_scaled_policy_and_catalog_units() -> None:
    assert admin_quantity(18000, "each") == "18 units"
    assert admin_quantity(1000, "each") == "1 unit"
    assert admin_quantity(1250, "gram") == "1.25 g"
    assert admin_quantity(None, "each") == "Not recorded"
