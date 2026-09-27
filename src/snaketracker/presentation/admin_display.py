"""Human-facing, deterministic formatting for the platform support console."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from snaketracker.domains.inventory.catalog import UNIT_BY_CODE, format_quantity_scaled


def admin_datetime(value: str | datetime | None, timezone: str | None = None) -> str:
    if not value:
        return "Not recorded"
    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        zone = ZoneInfo(timezone or "UTC")
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return "Not recorded"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone(zone)
    clock = local.strftime("%I:%M").lstrip("0")
    return f"{local:%b} {local.day}, {local.year} · {clock} {local:%p} {local:%Z}"


def admin_short_id(value: str | UUID | None) -> str:
    if value is None:
        return "Not recorded"
    identifier = str(value)
    try:
        if str(UUID(identifier)) != identifier.lower():
            return identifier
    except ValueError:
        return identifier
    return f"{identifier[:8]}…{identifier[-5:]}"


def admin_session_status(session: Mapping[str, Any], *, now: datetime | None = None) -> str:
    if session.get("revoked_at"):
        return "Revoked"
    instant = now or datetime.now(UTC)
    for key in ("idle_expires_at", "absolute_expires_at"):
        raw = session.get(key)
        if not raw:
            return "Expired"
        try:
            expiry = datetime.fromisoformat(str(raw))
        except ValueError:
            return "Expired"
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= instant:
            return "Expired"
    return "Active"


def admin_user_agent(value: str | None) -> str:
    if not value:
        return "Not recorded"
    agent = value.casefold()
    if "android" in agent:
        device = "Android"
    elif any(token in agent for token in ("iphone", "ipad", "ipod")):
        device = "iOS"
    elif "windows" in agent:
        device = "Windows"
    elif "mac os" in agent or "macintosh" in agent:
        device = "macOS"
    elif "linux" in agent:
        device = "Linux"
    else:
        device = "Unknown OS"
    mobile = "mobile" in agent or device in {"Android", "iOS"}
    if any(token in agent for token in ("edg/", "edga/", "edgios/", "edge/")):
        browser = "Edge"
    elif "crios/" in agent or "chrome/" in agent:
        browser = "Chrome Mobile" if mobile else "Chrome"
    elif "fxios/" in agent or "firefox/" in agent:
        browser = "Firefox"
    elif "safari/" in agent:
        browser = "Safari"
    else:
        browser = "Other browser"
    return f"{browser} · {device}"


def admin_quantity(
    quantity_scaled: int | None, unit_code: str | None, legacy_unit: str | None = None
) -> str:
    if quantity_scaled is None:
        return "Not recorded"
    quantity = format_quantity_scaled(quantity_scaled)
    if unit_code == "each":
        unit = "unit" if abs(quantity_scaled) == 1000 else "units"
    elif unit_code in UNIT_BY_CODE:
        unit = UNIT_BY_CODE[unit_code].symbol
        if abs(quantity_scaled) != 1000 and unit_code in {
            "pair",
            "pack",
            "package",
            "box",
            "case",
            "bag",
            "bottle",
            "jug",
            "bucket",
            "roll",
            "bale",
            "block",
            "brick",
        }:
            unit = {"box": "boxes"}.get(unit_code, f"{unit}s")
    else:
        unit = legacy_unit or "units"
    return f"{quantity} {unit}"
