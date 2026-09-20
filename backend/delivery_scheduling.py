"""Pure helpers for same-day delivery windows and kitchen-release timing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from restaurant_status import WEEKDAYS


def _timezone(settings: dict) -> ZoneInfo:
    try:
        return ZoneInfo(settings.get("timezone") or "Europe/Paris")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Paris")


def _at(local_day: datetime, value: str) -> datetime:
    hour, minute = (int(part) for part in value.split(":"))
    return local_day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _ceil_to_window(value: datetime, minutes: int) -> datetime:
    value = value.replace(second=0, microsecond=0)
    elapsed = value.hour * 60 + value.minute
    rounded = ((elapsed + minutes - 1) // minutes) * minutes
    return value.replace(hour=0, minute=0) + timedelta(minutes=rounded)


def delivery_slots(settings: dict, now: Optional[datetime] = None) -> list[dict[str, str]]:
    """Return valid same-day delivery arrival windows in restaurant local time."""
    if not settings.get("scheduled_delivery_enabled", True):
        return []

    tz = _timezone(settings)
    now_local = now.astimezone(tz) if now else datetime.now(tz)
    window_minutes = max(5, int(settings.get("delivery_window_minutes", 20) or 20))
    lead_minutes = max(0, int(settings.get("delivery_lead_minutes", 40) or 40))
    cutoff_minutes = max(0, int(settings.get("last_order_buffer_minutes", 0) or 0))
    day = settings.get("hours_per_day", {}).get(WEEKDAYS[now_local.weekday()], {})
    if not day.get("is_open"):
        return []

    earliest = now_local + timedelta(minutes=lead_minutes)
    slots: list[dict[str, str]] = []
    for current_range in day.get("ranges") or []:
        try:
            opening = _at(now_local, current_range["open"])
            closing = _at(now_local, current_range["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if closing <= opening:
            closing += timedelta(days=1)

        start = _ceil_to_window(max(earliest, opening + timedelta(minutes=lead_minutes)), window_minutes)
        last_end = closing - timedelta(minutes=cutoff_minutes)
        while start + timedelta(minutes=window_minutes) <= last_end:
            end = start + timedelta(minutes=window_minutes)
            slots.append(
                {
                    "start": start.astimezone(timezone.utc).isoformat(),
                    "end": end.astimezone(timezone.utc).isoformat(),
                    "label": f"{start:%H:%M} — {end:%H:%M}",
                }
            )
            start = end
    return slots


def validate_delivery_slot(settings: dict, scheduled_start: Optional[str]) -> Optional[dict[str, str]]:
    """Match an incoming ISO start time to a currently valid server-side slot."""
    if not scheduled_start:
        return None
    try:
        requested = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Créneau de livraison invalide.") from exc

    for slot in delivery_slots(settings):
        start = datetime.fromisoformat(slot["start"])
        if requested == start:
            return slot
    raise HTTPException(
        status_code=400,
        detail="Ce créneau n'est plus disponible. Choisis-en un autre.",
    )