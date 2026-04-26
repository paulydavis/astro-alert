"""Fetch seeing and transparency forecasts from 7timer.info (ASTRO product)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

ASTRO_URL = "https://www.7timer.info/bin/api.pl"
REQUEST_TIMEOUT = 10

# 7timer seeing scale: 1 (bad) – 8 (excellent)
# 7timer transparency scale: 1 (bad) – 8 (excellent)


@dataclass
class SeeingHour:
    time: datetime      # UTC, rounded to 3-hour blocks
    seeing: int         # 1–8
    transparency: int   # 1–8
    lifted_index: int   # atmospheric stability; higher = more stable


@dataclass
class SeeingResult:
    site_key: str
    fetched_at: datetime
    hours: list[SeeingHour]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def fetch_seeing(site_key: str, lat: float, lon: float) -> SeeingResult:
    """Fetch 7timer ASTRO forecast for lat/lon.

    Returns SeeingResult with error set if the API call fails — never raises.
    7timer returns data in 3-hour blocks starting from the nearest 3-hour UTC boundary.
    """
    params = {
        "lon": lon,
        "lat": lat,
        "ac": 0,
        "lang": "en",
        "output": "json",
        "tzshift": 0,
        "product": "astro",
    }

    fetched_at = datetime.now(timezone.utc)
    try:
        resp = requests.get(ASTRO_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return SeeingResult(site_key=site_key, fetched_at=fetched_at, hours=[], error=str(e))

    try:
        # init_date: "YYYYMMDDHH"
        init_str = str(data["init"])
        init_dt = datetime(
            int(init_str[0:4]),
            int(init_str[4:6]),
            int(init_str[6:8]),
            int(init_str[8:10]),
            tzinfo=timezone.utc,
        )
        from datetime import timedelta
        hours = []
        for entry in data["dataseries"]:
            offset_hours = int(entry["timepoint"])
            t = init_dt + timedelta(hours=offset_hours)
            hours.append(SeeingHour(
                time=t,
                seeing=int(entry["seeing"]),
                transparency=int(entry["transparency"]),
                lifted_index=int(entry["lifted_index"]),
            ))
    except (KeyError, TypeError, ValueError) as e:
        return SeeingResult(site_key=site_key, fetched_at=fetched_at, hours=[], error=f"Parse error: {e}")

    return SeeingResult(site_key=site_key, fetched_at=fetched_at, hours=hours)
