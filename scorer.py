"""Score a night's imaging conditions and produce a go/no-go recommendation."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from moon import MoonInfo
from seeing import SeeingResult
from weather import WeatherResult


@dataclass
class Score:
    total: int              # 0–100
    weather_score: int      # 0–40
    seeing_score: int       # 0–30
    moon_score: int         # 0–30
    go: bool                # True if total >= threshold
    summary: str
    warnings: list[str]


def _imaging_hours(target_date: date) -> set[datetime]:
    """Return the set of UTC datetimes covering 20:00–04:00 for target_date's night."""
    evening = {
        datetime(target_date.year, target_date.month, target_date.day, h, tzinfo=timezone.utc)
        for h in range(20, 24)
    }
    next_day = target_date + timedelta(days=1)
    early = {
        datetime(next_day.year, next_day.month, next_day.day, h, tzinfo=timezone.utc)
        for h in range(0, 5)
    }
    return evening | early


def _weather_score(result: WeatherResult, bortle: int, target_date: Optional[date] = None) -> tuple[int, list[str]]:
    """Score weather 0–40. Bortle-aware: dark sites penalize clouds more."""
    warnings = []
    if not result.ok or not result.hours:
        warnings.append("Weather data unavailable")
        return 20, warnings

    if target_date:
        window = _imaging_hours(target_date)
        night_hours = [h for h in result.hours if h.time.replace(minute=0, second=0, microsecond=0) in window]
    else:
        night_hours = result.hours
    if not night_hours:
        night_hours = result.hours

    avg_cloud = sum(h.cloud_cover_pct for h in night_hours) / len(night_hours)
    any_precip = any(h.precip_mm > 0.1 for h in night_hours)
    avg_wind = sum(h.wind_speed_kmh for h in night_hours) / len(night_hours)
    avg_humidity = sum(h.humidity_pct for h in night_hours) / len(night_hours)
    min_dew_gap = min(h.temp_c - h.dew_point_c for h in night_hours)

    cloud_weight = 1.2 if bortle <= 4 else 1.0
    if avg_cloud < 10:
        cloud_pts = 40
    elif avg_cloud < 25:
        cloud_pts = 32
    elif avg_cloud < 50:
        cloud_pts = 18
        warnings.append(f"Partly cloudy ({avg_cloud:.0f}% avg)")
    elif avg_cloud < 75:
        cloud_pts = 8
        warnings.append(f"Mostly cloudy ({avg_cloud:.0f}% avg)")
    else:
        cloud_pts = 0
        warnings.append(f"Overcast ({avg_cloud:.0f}% avg)")
    cloud_pts = int(min(40, cloud_pts * cloud_weight))

    if any_precip:
        cloud_pts = 0
        warnings.append("Precipitation expected")

    if avg_wind > 30:
        cloud_pts = max(0, cloud_pts - 10)
        warnings.append(f"High wind ({avg_wind:.0f} km/h avg)")
    elif avg_wind > 20:
        cloud_pts = max(0, cloud_pts - 5)
        warnings.append(f"Moderate wind ({avg_wind:.0f} km/h avg)")

    if min_dew_gap < 2:
        warnings.append(f"Dew risk: temp/dew gap only {min_dew_gap:.1f}°C")
    if avg_humidity > 90:
        warnings.append(f"High humidity ({avg_humidity:.0f}%)")

    return cloud_pts, warnings


def _seeing_score(result: SeeingResult, target_date: Optional[date] = None) -> tuple[int, list[str]]:
    """Score seeing/transparency 0–30."""
    warnings = []
    if not result.ok or not result.hours:
        warnings.append("Seeing data unavailable")
        return 15, warnings

    if target_date:
        window = _imaging_hours(target_date)
        night_hours = [h for h in result.hours if h.time.replace(minute=0, second=0, microsecond=0) in window]
    else:
        night_hours = result.hours
    if not night_hours:
        night_hours = result.hours

    avg_seeing = sum(h.seeing for h in night_hours) / len(night_hours)
    avg_transparency = sum(h.transparency for h in night_hours) / len(night_hours)

    seeing_pts = int((avg_seeing / 8) * 15)
    transp_pts = int((avg_transparency / 8) * 15)

    if avg_seeing < 3:
        warnings.append(f"Poor seeing ({avg_seeing:.1f}/8)")
    if avg_transparency < 3:
        warnings.append(f"Poor transparency ({avg_transparency:.1f}/8)")

    return seeing_pts + transp_pts, warnings


def _moon_score(info: MoonInfo) -> tuple[int, list[str]]:
    """Score moon interference 0–30 (30 = no moon impact)."""
    warnings = []
    phase = info.phase_pct

    if phase < 10:
        pts = 30
    elif phase < 25:
        pts = 24
        warnings.append(f"Crescent moon ({phase:.0f}% illuminated)")
    elif phase < 50:
        pts = 15
        warnings.append(f"Quarter moon ({phase:.0f}% illuminated)")
    elif phase < 75:
        pts = 6
        warnings.append(f"Gibbous moon ({phase:.0f}% illuminated)")
    else:
        pts = 0
        warnings.append(f"Bright moon ({phase:.0f}% illuminated)")

    if info.is_up_at_midnight and phase > 20:
        pts = max(0, pts - 5)
        warnings.append("Moon up at midnight")

    return pts, warnings


def score_night(
    weather: WeatherResult,
    seeing: SeeingResult,
    moon: MoonInfo,
    bortle: int,
    target_date: Optional[date] = None,
    go_threshold: int = 55,
) -> Score:
    w_pts, w_warn = _weather_score(weather, bortle, target_date)
    s_pts, s_warn = _seeing_score(seeing, target_date)
    m_pts, m_warn = _moon_score(moon)

    total = w_pts + s_pts + m_pts
    all_warnings = w_warn + s_warn + m_warn
    go = total >= go_threshold

    if go:
        if total >= 80:
            summary = "Excellent night — go image."
        elif total >= 65:
            summary = "Good night — go image."
        else:
            summary = "Marginal but go-able — worth setting up."
    else:
        summary = "No-go tonight."

    return Score(
        total=total,
        weather_score=w_pts,
        seeing_score=s_pts,
        moon_score=m_pts,
        go=go,
        summary=summary,
        warnings=all_warnings,
    )
