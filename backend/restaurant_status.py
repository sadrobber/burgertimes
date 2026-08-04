"""Restaurant open/closing_soon/closed status engine (pure function)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_LABELS_FR = {
    "mon": "Lundi",
    "tue": "Mardi",
    "wed": "Mercredi",
    "thu": "Jeudi",
    "fri": "Vendredi",
    "sat": "Samedi",
    "sun": "Dimanche",
}


def _parse_hm(s: str) -> tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def _time_at(base: datetime, hm: str) -> datetime:
    hh, mm = _parse_hm(hm)
    return base.replace(hour=hh, minute=mm, second=0, microsecond=0)


def compute_status(settings: dict, now: Optional[datetime] = None) -> Dict[str, Any]:
    tz_name = settings.get("timezone") or "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Paris")

    now_local = (now.astimezone(tz) if now else datetime.now(tz))
    now_str = now_local.strftime("%H:%M")

    eta_min = settings.get("eta_default_min", 20)
    eta_max = settings.get("eta_default_max", 30)
    too_busy = bool(settings.get("too_busy", False))
    if too_busy:
        eta_min = settings.get("too_busy_eta_min", eta_min + 20)
        eta_max = settings.get("too_busy_eta_max", eta_max + 20)

    if settings.get("force_closed"):
        return _closed(now_str, "force_closed", eta_min, eta_max, too_busy, settings, now_local)

    hours = settings.get("hours_per_day") or {}
    weekday_key = WEEKDAYS[now_local.weekday()]
    day_cfg = hours.get(weekday_key) or {}

    if not day_cfg.get("is_open"):
        return _closed(now_str, "day_off", eta_min, eta_max, too_busy, settings, now_local)

    ranges = day_cfg.get("ranges") or []
    buffer_min = int(settings.get("last_order_buffer_minutes", 15) or 0)
    closing_soon_win = int(settings.get("closing_soon_window_minutes", 30) or 0)

    current_range = None
    for r in ranges:
        try:
            open_dt = _time_at(now_local, r["open"])
            close_dt = _time_at(now_local, r["close"])
        except Exception:  # noqa: BLE001
            continue
        # overnight range support
        if close_dt <= open_dt:
            close_dt = close_dt + timedelta(days=1)
        if open_dt <= now_local < close_dt:
            current_range = (open_dt, close_dt)
            break

    if current_range is None:
        # before first opening today?
        for r in ranges:
            try:
                open_dt = _time_at(now_local, r["open"])
            except Exception:  # noqa: BLE001
                continue
            if now_local < open_dt:
                return {
                    "state": "closed",
                    "reason": "before_open",
                    "now_local_str": now_str,
                    "next_open_at_local": r["open"],
                    "next_open_day": "today",
                    "eta_min": eta_min,
                    "eta_max": eta_max,
                    "too_busy": too_busy,
                }
        # after last closing → find next day
        nxt = _find_next_opening(hours, now_local)
        return {
            "state": "closed",
            "reason": "after_close",
            "now_local_str": now_str,
            "next_open_at_local": nxt["at"] if nxt else None,
            "next_open_day": nxt["day"] if nxt else None,
            "eta_min": eta_min,
            "eta_max": eta_max,
            "too_busy": too_busy,
        }

    open_dt, close_dt = current_range
    if now_local + timedelta(minutes=buffer_min) >= close_dt:
        return {
            "state": "closed",
            "reason": "after_cutoff",
            "now_local_str": now_str,
            "closing_at_local": close_dt.strftime("%H:%M"),
            "eta_min": eta_min,
            "eta_max": eta_max,
            "too_busy": too_busy,
        }

    if (close_dt - now_local) <= timedelta(minutes=closing_soon_win):
        return {
            "state": "closing_soon",
            "reason": "closing_soon",
            "now_local_str": now_str,
            "closing_at_local": close_dt.strftime("%H:%M"),
            "eta_min": eta_min,
            "eta_max": eta_max,
            "too_busy": too_busy,
        }

    return {
        "state": "open",
        "reason": "open",
        "now_local_str": now_str,
        "closing_at_local": close_dt.strftime("%H:%M"),
        "eta_min": eta_min,
        "eta_max": eta_max,
        "too_busy": too_busy,
    }


def _closed(now_str, reason, eta_min, eta_max, too_busy, settings, now_local) -> Dict[str, Any]:
    nxt = _find_next_opening(settings.get("hours_per_day") or {}, now_local)
    return {
        "state": "closed",
        "reason": reason,
        "now_local_str": now_str,
        "next_open_at_local": nxt["at"] if nxt else None,
        "next_open_day": nxt["day"] if nxt else None,
        "eta_min": eta_min,
        "eta_max": eta_max,
        "too_busy": too_busy,
    }


def _find_next_opening(hours: dict, now_local: datetime) -> Optional[Dict[str, str]]:
    for offset in range(1, 8):
        d = now_local + timedelta(days=offset)
        weekday_key = WEEKDAYS[d.weekday()]
        cfg = hours.get(weekday_key) or {}
        if not cfg.get("is_open"):
            continue
        ranges = cfg.get("ranges") or []
        if not ranges:
            continue
        first = ranges[0]
        day_label = "tomorrow" if offset == 1 else WEEKDAY_LABELS_FR.get(weekday_key, weekday_key)
        return {"at": first.get("open"), "day": day_label}
    return None
