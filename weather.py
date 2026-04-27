"""Fetch hourly weather from Open-Meteo for a given site."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10


@dataclass
class HourlyWeather:
    time: datetime          # UTC
    cloud_cover_pct: int    # 0–100
    precip_mm: float        # precipitation (mm)
    wind_speed_kmh: float   # 10 m wind speed
    humidity_pct: int       # relative humidity %
    dew_point_c: float      # dew point °C
    temp_c: float           # 2 m temperature °C


@dataclass
class WeatherResult:
    site_key: str
    fetched_at: datetime    # UTC
    hours: list[HourlyWeather]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def fetch_weather(site_key: str, lat: float, lon: float, target_date: Optional[date] = None, end_date: Optional[date] = None) -> WeatherResult:
    """Fetch hourly weather for lat/lon.

    When end_date is provided, fetches from target_date through end_date (inclusive).
    When end_date is None, defaults to target_date + 1 day (original behavior).
    Returns WeatherResult with error set if the API call fails — never raises.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()
    if end_date is None:
        end_date = target_date + timedelta(days=1)

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "cloud_cover,precipitation,wind_speed_10m,relative_humidity_2m,dew_point_2m,temperature_2m",
        "start_date": target_date.isoformat(),
        "end_date": end_date.isoformat(),
        "wind_speed_unit": "kmh",
        "timezone": "UTC",
    }

    fetched_at = datetime.now(timezone.utc)
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return WeatherResult(site_key=site_key, fetched_at=fetched_at, hours=[], error=str(e))

    try:
        hourly = data["hourly"]
        hours = [
            HourlyWeather(
                time=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                cloud_cover_pct=int(cc),
                precip_mm=float(pr),
                wind_speed_kmh=float(ws),
                humidity_pct=int(rh),
                dew_point_c=float(dp),
                temp_c=float(tmp),
            )
            for t, cc, pr, ws, rh, dp, tmp in zip(
                hourly["time"],
                hourly["cloud_cover"],
                hourly["precipitation"],
                hourly["wind_speed_10m"],
                hourly["relative_humidity_2m"],
                hourly["dew_point_2m"],
                hourly["temperature_2m"],
            )
        ]
    except (KeyError, TypeError, ValueError) as e:
        return WeatherResult(site_key=site_key, fetched_at=fetched_at, hours=[], error=f"Parse error: {e}")

    return WeatherResult(site_key=site_key, fetched_at=fetched_at, hours=hours)
