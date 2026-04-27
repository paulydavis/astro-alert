"""72-hour astrophotography forecast chart — color mapping and HTML generation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChartData:
    site_name: str
    start_dt: datetime              # UTC, hour 0 of first day
    cloud: list                     # int 0–100 %, or None per hour, 72 entries
    seeing: list                    # float 1–8, or None per hour, 72 entries
    transparency: list              # float 1–8, or None per hour, 72 entries
    wind: list                      # float km/h, or None per hour, 72 entries
    humidity: list                  # int 0–100 %, or None per hour, 72 entries
    temperature: list               # float °C, or None per hour, 72 entries
    precipitation: list             # float mm, or None per hour, 72 entries
    moon_pct: list                  # int 0–100 illumination %, 72 entries
    moon_events: dict               # {hour_index: "rise" | "set"}
    errors: list                    # data source failure messages


# ── Color palette ────────────────────────────────────────────────────────────

_DARK_BLUE = (0, 0, 139)
_WHITE     = (255, 255, 255)
_ORANGE    = (255, 140, 0)
_RED       = (200, 30, 30)
_GRAY_CLEAR = (180, 180, 180)
_GRAY_RAIN  = (160, 20, 20)
_MISSING   = "#444444"


def _lerp(c1: tuple, c2: tuple, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def cloud_color(pct: int) -> str:
    """0% → dark blue (clear), 100% → white (overcast)."""
    return _lerp(_DARK_BLUE, _WHITE, pct / 100)


def seeing_color(val: float) -> str:
    """8 → dark blue (excellent), 1 → white (poor)."""
    return _lerp(_DARK_BLUE, _WHITE, 1.0 - (min(max(val, 1), 8) - 1) / 7)


def transparency_color(val: float) -> str:
    """8 → dark blue (excellent), 1 → white (poor)."""
    return seeing_color(val)


def wind_color(kmh: float) -> str:
    """0 → dark blue (calm), 20 → orange (moderate), 30+ → red (high)."""
    if kmh <= 20:
        return _lerp(_DARK_BLUE, _ORANGE, kmh / 20)
    return _lerp(_ORANGE, _RED, min((kmh - 20) / 20, 1.0))


def humidity_color(pct: int) -> str:
    """<40% → dark blue, >90% → white."""
    return _lerp(_DARK_BLUE, _WHITE, min(max(pct - 40, 0), 50) / 50)


def temperature_color(c: float) -> str:
    """Blue (≤-15°C) → gray (0°C) → orange (≥30°C)."""
    _COLD = (30, 30, 200)
    _MILD = (100, 100, 100)
    _WARM = (220, 100, 30)
    if c <= 0:
        return _lerp(_MILD, _COLD, min(-c / 15, 1.0))
    return _lerp(_MILD, _WARM, min(c / 30, 1.0))


def precipitation_color(mm: float) -> str:
    """0mm → light gray, ≥1mm → dark red."""
    return _lerp(_GRAY_CLEAR, _GRAY_RAIN, min(mm, 1.0))


def moon_color(pct: int) -> str:
    """New moon → dark gray, full moon → light gray."""
    v = int(60 + pct * 0.9)
    return f"#{v:02x}{v:02x}{v:02x}"
