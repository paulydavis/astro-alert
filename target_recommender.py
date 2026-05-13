"""Recommend deep-sky objects for a given imaging night."""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import ephem

_TARGETS_FILE = Path(__file__).parent / "targets.json"
_log = logging.getLogger(__name__)


@dataclass
class TargetResult:
    name: str
    common_name: str
    type: str
    magnitude: float
    size_arcmin: float
    description: str
    peak_alt_deg: float
    hours_visible: float
    transit_utc: Optional[datetime]
    ra: str = ""
    dec: str = ""
    window_start_utc: Optional[datetime] = None
    window_end_utc: Optional[datetime] = None
    peak_az_deg: float = 0.0


_IMAGING_TYPES = {
    "Emission Nebula", "Galaxy", "Globular Cluster", "Open Cluster",
    "Planetary Nebula", "Reflection Nebula", "Supernova Remnant",
}


def get_nightly_targets(
    lat: float,
    lon: float,
    imaging_window: set,
    min_alt_deg: float = 25.0,
    min_hours: float = 2.0,
    max_results: int = 10,
) -> list[TargetResult]:
    """Return up to max_results imaging targets visible during imaging_window, sorted by peak altitude.

    Double stars and other non-imaging types are excluded.
    """
    try:
        with open(_TARGETS_FILE) as f:
            raw_targets = json.load(f)
    except Exception as exc:
        _log.warning("Failed to load targets.json: %s", exc)
        return []

    if not imaging_window:
        return []

    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.pressure = 0
    obs.horizon = "0"

    sorted_window = sorted(imaging_window)
    results: list[TargetResult] = []

    for target in raw_targets:
        if target.get("type") not in _IMAGING_TYPES:
            continue
        try:
            body = ephem.FixedBody()
            body._ra    = target["ra"]
            body._dec   = target["dec"]
            body._epoch = ephem.J2000

            altitudes: list[tuple[float, float, datetime]] = []
            for dt in sorted_window:
                obs.date = ephem.Date(dt.replace(tzinfo=None))
                body.compute(obs)
                altitudes.append((math.degrees(float(body.alt)), math.degrees(float(body.az)), dt))

            above = [(alt, az, dt) for alt, az, dt in altitudes if alt >= min_alt_deg]
            hours_above = len(above)
            if hours_above < min_hours:
                continue

            peak_alt, peak_az, transit_dt = max(altitudes, key=lambda x: x[0])
            win_start = above[0][2] if above else None
            win_end   = above[-1][2] if above else None
            results.append(TargetResult(
                name=target["name"],
                common_name=target["common_name"],
                type=target["type"],
                magnitude=float(target["magnitude"]),
                size_arcmin=float(target["size_arcmin"]),
                description=target["description"],
                peak_alt_deg=round(peak_alt, 1),
                hours_visible=float(hours_above),
                transit_utc=transit_dt,
                ra=target.get("ra", ""),
                dec=target.get("dec", ""),
                window_start_utc=win_start,
                window_end_utc=win_end,
                peak_az_deg=round(peak_az, 1),
            ))
        except Exception as exc:
            _log.warning("Skipping target %s: %s", target.get("name", "?"), exc)

    window_start = min(imaging_window)
    window_end   = max(imaging_window)
    results.sort(key=lambda r: _photo_score(r, window_start, window_end), reverse=True)
    return _diverse(results, max_results)


# Max slots per broad category — prevents any single type sweeping the whole card
_TYPE_CAPS = {
    "Emission Nebula":   3,
    "Supernova Remnant": 2,
    "Galaxy":            7,
    "Globular Cluster":  3,
    "Open Cluster":      2,
    "Planetary Nebula":  2,
    "Reflection Nebula": 2,
}


def _diverse(ranked: list, n: int) -> list:
    """Pick up to n results while respecting per-type caps for variety."""
    counts: dict[str, int] = {}
    chosen = []
    for r in ranked:
        cap = _TYPE_CAPS.get(r.type, n)
        if counts.get(r.type, 0) < cap:
            chosen.append(r)
            counts[r.type] = counts.get(r.type, 0) + 1
        if len(chosen) == n:
            break
    return chosen


def _photo_score(r: TargetResult, window_start: datetime, window_end: datetime) -> float:
    """Composite score for OSC astrophotography.

    Factors: object type, angular size, brightness, altitude, and timing.
    Objects peaking in the first half of the night score higher than those
    that only reach their best altitude near dawn.
    """
    type_weight = {
        "Emission Nebula":   1.30,
        "Supernova Remnant": 1.15,
        "Reflection Nebula": 1.08,
        "Galaxy":            1.00,
        "Globular Cluster":  0.90,
        "Open Cluster":      0.85,
        "Planetary Nebula":  0.70,
    }.get(r.type, 1.0)

    size = r.size_arcmin
    if size >= 30:
        size_bonus = 1.12
    elif size >= 10:
        size_bonus = 1.06
    elif size < 3:
        size_bonus = 0.85
    else:
        size_bonus = 1.0

    bright_bonus = 1.08 if r.magnitude <= 6.5 else (1.03 if r.magnitude <= 8.5 else 1.0)

    alt_factor = r.peak_alt_deg if r.peak_alt_deg >= 35 else r.peak_alt_deg * 0.88

    # Timing bonus: objects peaking in the first 60% of the dark window are
    # prime-time targets; those peaking in the last 20% get a penalty.
    timing = 1.0
    if r.transit_utc:
        span = (window_end - window_start).total_seconds()
        if span > 0:
            frac = (r.transit_utc - window_start).total_seconds() / span
            frac = max(0.0, min(1.0, frac))
            if frac <= 0.60:
                timing = 1.20   # prime time
            elif frac <= 0.80:
                timing = 1.00   # middle of night, neutral
            else:
                timing = 0.80   # near dawn

    # M51/M101: exceptional spring spirals that fill the FOV
    if r.name in ("M51", "M101"):
        alt_factor *= 1.35

    # Iconic summer nebulae — classic targets even when low and late in May
    if r.name in ("M8", "M16", "M17", "M20"):
        alt_factor *= 2.0

    return alt_factor * type_weight * size_bonus * bright_bonus * timing
