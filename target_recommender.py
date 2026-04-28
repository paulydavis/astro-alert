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


def get_nightly_targets(
    lat: float,
    lon: float,
    imaging_window: set,
    min_alt_deg: float = 25.0,
    min_hours: float = 2.0,
    max_results: int = 10,
) -> list[TargetResult]:
    """Return up to max_results targets visible during imaging_window, sorted by peak altitude."""
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
        try:
            body = ephem.FixedBody()
            body._ra    = target["ra"]
            body._dec   = target["dec"]
            body._epoch = ephem.J2000

            altitudes: list[tuple[float, datetime]] = []
            for dt in sorted_window:
                obs.date = ephem.Date(dt.replace(tzinfo=None))
                body.compute(obs)
                altitudes.append((math.degrees(float(body.alt)), dt))

            hours_above = sum(1 for alt, _ in altitudes if alt >= min_alt_deg)
            if hours_above < min_hours:
                continue

            peak_alt, transit_dt = max(altitudes, key=lambda x: x[0])
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
            ))
        except Exception as exc:
            _log.warning("Skipping target %s: %s", target.get("name", "?"), exc)

    results.sort(key=lambda r: r.peak_alt_deg, reverse=True)
    return results[:max_results]
