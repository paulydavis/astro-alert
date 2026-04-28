"""Moon calculations using ephem."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import ephem


@dataclass
class MoonInfo:
    phase_pct: float        # 0–100 illumination
    rise_utc: Optional[datetime]
    set_utc: Optional[datetime]
    transit_utc: Optional[datetime]
    is_up_at_midnight: bool


def get_sun_times(lat: float, lon: float, target_date: date) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return (sunset_utc, sunrise_utc) for the night starting on target_date.

    Searches for the next sunset after local noon, then the next sunrise after that.
    Returns (None, None) on polar extremes where the sun never sets or rises.
    """
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.pressure = 0
    obs.horizon = "-0:34"

    def _to_utc(ephem_date) -> Optional[datetime]:
        if ephem_date is None:
            return None
        return datetime.strptime(str(ephem_date), "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)

    noon = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0)
    obs.date = ephem.Date(noon)
    sun = ephem.Sun()

    try:
        sunset_utc = _to_utc(obs.next_setting(sun))
    except (ephem.NeverUpError, ephem.AlwaysUpError):
        return None, None

    if sunset_utc is None:
        return None, None

    obs.date = ephem.Date(sunset_utc.replace(tzinfo=None))
    try:
        sunrise_utc = _to_utc(obs.next_rising(sun))
    except (ephem.NeverUpError, ephem.AlwaysUpError):
        sunrise_utc = None

    return sunset_utc, sunrise_utc


def get_moon_info(lat: float, lon: float, target_date: Optional[date] = None) -> MoonInfo:
    """Compute moon phase and rise/set for lat/lon on target_date (default: today UTC)."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.pressure = 0        # disable atmospheric refraction correction
    obs.horizon = "-0:34"   # standard horizon dip

    # Compute at local midnight UTC of that date
    midnight = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    obs.date = ephem.Date(midnight)

    moon = ephem.Moon(obs)
    phase_pct = float(moon.phase)

    def _to_utc(ephem_date) -> Optional[datetime]:
        if ephem_date is None:
            return None
        return datetime.strptime(str(ephem_date), "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)

    try:
        rise_utc = _to_utc(obs.next_rising(moon))
    except ephem.NeverUpError:
        rise_utc = None
    except ephem.AlwaysUpError:
        rise_utc = None

    try:
        set_utc = _to_utc(obs.next_setting(moon))
    except ephem.NeverUpError:
        set_utc = None
    except ephem.AlwaysUpError:
        set_utc = None

    try:
        transit_utc = _to_utc(obs.next_transit(moon))
    except (ephem.NeverUpError, ephem.AlwaysUpError):
        transit_utc = None

    # Check if moon is above horizon at local midnight
    obs.date = ephem.Date(midnight)
    moon.compute(obs)
    is_up_at_midnight = float(moon.alt) > 0

    return MoonInfo(
        phase_pct=phase_pct,
        rise_utc=rise_utc,
        set_utc=set_utc,
        transit_utc=transit_utc,
        is_up_at_midnight=is_up_at_midnight,
    )


def compute_imaging_window(lat: float, lon: float, target_date: date) -> set:
    """Return the set of UTC hour datetimes covering sunset→sunrise for target_date.

    Falls back to 20:00–04:00 UTC if sun times are unavailable (polar extremes).
    """
    sunset, sunrise = get_sun_times(lat, lon, target_date)
    if sunset and sunrise:
        start = sunset.replace(minute=0, second=0, microsecond=0)
        end   = sunrise.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        hours: set = set()
        t = start
        while t <= end:
            hours.add(t)
            t += timedelta(hours=1)
        return hours
    ev = {
        datetime(target_date.year, target_date.month, target_date.day,
                 h, tzinfo=timezone.utc)
        for h in range(20, 24)
    }
    nd = target_date + timedelta(days=1)
    ea = {
        datetime(nd.year, nd.month, nd.day, h, tzinfo=timezone.utc)
        for h in range(0, 5)
    }
    return ev | ea
