"""72-hour astrophotography forecast chart — color mapping and HTML generation."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from weather import fetch_weather
from seeing import fetch_seeing
from moon import get_moon_info


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


def build_chart_data(site, hours: int = 72) -> ChartData:
    """Assemble 72-hour ChartData for a site by fetching weather, seeing, and moon data."""
    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=2)
    start_dt = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc)
    errors = []

    # ── Weather (one API call, 3 days) ────────────────────────────────────────
    weather = fetch_weather(site.key, site.lat, site.lon,
                            target_date=today, end_date=end_date)
    if not weather.ok:
        errors.append(f"Weather: {weather.error}")

    hour_map = {
        h.time.replace(minute=0, second=0, microsecond=0): h
        for h in weather.hours
    }

    cloud, wind, humidity, temperature, precipitation = [], [], [], [], []
    for i in range(hours):
        t = start_dt + timedelta(hours=i)
        hw = hour_map.get(t)
        cloud.append(hw.cloud_cover_pct if hw else None)
        wind.append(hw.wind_speed_kmh if hw else None)
        humidity.append(hw.humidity_pct if hw else None)
        temperature.append(hw.temp_c if hw else None)
        precipitation.append(hw.precip_mm if hw else None)

    # ── Seeing (3-hour blocks from 7timer) ───────────────────────────────────
    seeing_result = fetch_seeing(site.key, site.lat, site.lon)
    if not seeing_result.ok:
        errors.append(f"Seeing: {seeing_result.error}")

    seeing_map = {
        sh.time.replace(minute=0, second=0, microsecond=0): sh
        for sh in seeing_result.hours
    }

    seeing, transparency = [], []
    for i in range(hours):
        t = start_dt + timedelta(hours=i)
        t3 = t.replace(hour=(t.hour // 3) * 3)
        sh = seeing_map.get(t3)
        seeing.append(float(sh.seeing) if sh else None)
        transparency.append(float(sh.transparency) if sh else None)

    # ── Moon (one call per day, spread across 24 hours) ──────────────────────
    moon_pct: list = []
    moon_events: dict = {}
    num_days = (hours + 23) // 24
    for day_offset in range(num_days):
        d = today + timedelta(days=day_offset)
        info = get_moon_info(site.lat, site.lon, target_date=d)
        moon_pct.extend([int(info.phase_pct)] * 24)
        for event_dt, label in [(info.rise_utc, "rise"), (info.set_utc, "set")]:
            if event_dt:
                delta = event_dt - start_dt
                idx = int(delta.total_seconds() // 3600)
                if 0 <= idx < hours:
                    moon_events[idx] = label

    return ChartData(
        site_name=site.name,
        start_dt=start_dt,
        cloud=cloud,
        seeing=seeing,
        transparency=transparency,
        wind=wind,
        humidity=humidity,
        temperature=temperature,
        precipitation=precipitation,
        moon_pct=moon_pct[:hours],
        moon_events=moon_events,
        errors=errors,
    )


# ── Row definitions for HTML table ───────────────────────────────────────────

_ROWS = [
    ("Cloud Cover",  "cloud",         cloud_color,         lambda v: f"{v}%"),
    ("Seeing",       "seeing",        seeing_color,        lambda v: f"{v:.0f}/8"),
    ("Transparency", "transparency",  transparency_color,  lambda v: f"{v:.0f}/8"),
    ("Wind",         "wind",          wind_color,          lambda v: f"{v:.0f} km/h"),
    ("Humidity",     "humidity",      humidity_color,      lambda v: f"{v}%"),
    ("Temperature",  "temperature",   temperature_color,   lambda v: f"{v:.1f}°C"),
    ("Precip",       "precipitation", precipitation_color, lambda v: f"{v:.1f} mm"),
    ("Moon",         "moon_pct",      moon_color,          lambda v: f"{v}%"),
]

_CELL_W  = 18
_CELL_H  = 24
_LABEL_W = 120


def render_html(data: ChartData) -> str:
    """Return a complete HTML document containing the 72-hour forecast table."""
    hours = len(data.cloud)
    num_days = (hours + 23) // 24

    lines = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        f"<title>Astro Chart — {data.site_name}</title>",
        "</head>",
        '<body style="background:#0d1117;color:#c9d1d9;font-family:monospace">',
        f'<h2 style="margin:16px 0 8px">{data.site_name} — 72-Hour Forecast</h2>',
        '<table style="border-collapse:collapse;font-size:10px">',
    ]

    # ── Date header row ──────────────────────────────────────────────────────
    lines.append("<tr>")
    lines.append(f'<td style="width:{_LABEL_W}px"></td>')
    for day in range(num_days):
        dt = data.start_dt + timedelta(hours=day * 24)
        label = dt.strftime("%a %b %-d")
        lines.append(
            f'<td colspan="24" style="text-align:center;font-weight:bold;'
            f'padding:2px 0;color:#58a6ff">{label}</td>'
        )
    lines.append("</tr>")

    # ── Hour labels row ──────────────────────────────────────────────────────
    lines.append("<tr>")
    lines.append(f'<td style="width:{_LABEL_W}px"></td>')
    for i in range(hours):
        h = i % 24
        lines.append(
            f'<td style="width:{_CELL_W}px;text-align:center;'
            f'color:#8b949e;font-size:9px">{h:02d}</td>'
        )
    lines.append("</tr>")

    # ── Data rows ────────────────────────────────────────────────────────────
    for label, field_name, color_fn, fmt_fn in _ROWS:
        values = getattr(data, field_name)
        lines.append("<tr>")
        lines.append(
            f'<td style="padding-right:8px;white-space:nowrap;'
            f'font-size:11px;color:#c9d1d9">{label}</td>'
        )
        for i, val in enumerate(values):
            if val is None:
                bg    = _MISSING
                title = "N/A"
                text  = ""
            else:
                bg    = color_fn(val)
                title = fmt_fn(val)
                text  = ""

            if field_name == "moon_pct" and i in data.moon_events:
                text = "▲" if data.moon_events[i] == "rise" else "▼"

            cell_style = (
                f"background:{bg};width:{_CELL_W}px;height:{_CELL_H}px;"
                f"text-align:center;font-size:9px;color:#fff"
            )
            lines.append(f'<td title="{title}" style="{cell_style}">{text}</td>')
        lines.append("</tr>")

    lines += ["</table>"]

    if data.errors:
        err_html = "<br>".join(data.errors)
        lines.append(f'<p style="color:#e3b341;font-size:11px">⚠ Data gaps: {err_html}</p>')

    lines += ["</body></html>"]
    return "\n".join(lines)
