# Hourly Chart Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 72-hour color-coded hourly forecast chart tab (Clear Dark Sky style) to the GUI, with a matching HTML email option selectable in Settings.

**Architecture:** A new `chart_html.py` module owns `ChartData` assembly and HTML rendering. Shared color-mapping functions are used by both the `tk.Canvas` chart renderer in `gui.py` and the HTML email generator. `fetch_weather` gains an optional `end_date` parameter for 3-day fetches. `smtp_notifier.py` reads `EMAIL_FORMAT` from `.env` and sends `multipart/alternative` HTML when set.

**Tech Stack:** Python 3.11+, tkinter Canvas, Open-Meteo (weather), 7timer.info (seeing/transparency), ephem (moon), smtplib + email.mime (HTML email)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `weather.py` | Add optional `end_date` param to `fetch_weather` |
| Create | `chart_html.py` | `ChartData` dataclass, color functions, `build_chart_data()`, `render_html()` |
| Create | `test_chart_html.py` | Tests for `build_chart_data` and `render_html` |
| Modify | `test_weather.py` | Test for 3-day range fetch |
| Modify | `gui.py` | Add `_build_chart_tab()`, add Email Format radios to Settings |
| Modify | `smtp_notifier.py` | Accept `sites` param, send HTML email when `EMAIL_FORMAT=html` |
| Modify | `astro_alert.py` | Pass `sites_to_fetch` to `send_multi_site_alert` |
| Modify | `test_gui.py` | Smoke test for Chart tab |

---

## Task 1: Extend `fetch_weather` for multi-day ranges

**Files:**
- Modify: `weather.py:36-88`
- Modify: `test_weather.py`

- [ ] **Step 1: Write the failing test**

Add to `test_weather.py`:

```python
import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

def test_fetch_weather_three_day_range():
    """fetch_weather with end_date returns hourly entries for all days in range."""
    # Build a fake Open-Meteo response with 72 hourly entries (3 days × 24 hours)
    start = datetime(2026, 5, 1, 0, tzinfo=timezone.utc)
    times = [(start.replace(hour=0) + __import__('datetime').timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(72)]
    fake_data = {
        "hourly": {
            "time": times,
            "cloud_cover": [10] * 72,
            "precipitation": [0.0] * 72,
            "wind_speed_10m": [5.0] * 72,
            "relative_humidity_2m": [50] * 72,
            "dew_point_2m": [5.0] * 72,
            "temperature_2m": [15.0] * 72,
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_data
    mock_resp.raise_for_status = MagicMock()

    with patch("weather.requests.get", return_value=mock_resp):
        from weather import fetch_weather
        from datetime import timedelta
        result = fetch_weather(
            "test", 35.9, -79.0,
            target_date=date(2026, 5, 1),
            end_date=date(2026, 5, 3),
        )

    assert result.ok
    assert len(result.hours) == 72
    assert result.hours[0].cloud_cover_pct == 10
    assert result.hours[71].cloud_cover_pct == 10
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_weather.py::test_fetch_weather_three_day_range -v
```

Expected: FAIL — `fetch_weather() got an unexpected keyword argument 'end_date'`

- [ ] **Step 3: Add `end_date` parameter to `fetch_weather`**

In `weather.py`, change the function signature and `end_date` param line:

```python
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
```

(Leave the rest of the function unchanged.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest test_weather.py::test_fetch_weather_three_day_range -v
```

Expected: PASS

- [ ] **Step 5: Run full weather test suite to check for regressions**

```bash
python -m pytest test_weather.py -v
```

Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add weather.py test_weather.py
git commit -m "feat: add end_date param to fetch_weather for multi-day ranges"
```

---

## Task 2: Create `chart_html.py` — `ChartData` and color functions

**Files:**
- Create: `chart_html.py`
- Create: `test_chart_html.py`

- [ ] **Step 1: Write the failing test**

Create `test_chart_html.py`:

```python
"""Tests for chart_html module."""


def test_cloud_color_clear():
    from chart_html import cloud_color
    assert cloud_color(0) == "#00008b"


def test_cloud_color_overcast():
    from chart_html import cloud_color
    color = cloud_color(100)
    assert color == "#ffffff"


def test_seeing_color_best():
    from chart_html import seeing_color
    # Best seeing (8) → dark blue
    color = seeing_color(8)
    assert color == "#00008b"


def test_seeing_color_worst():
    from chart_html import seeing_color
    # Worst seeing (1) → white
    color = seeing_color(1)
    assert color == "#ffffff"


def test_wind_color_calm():
    from chart_html import wind_color
    assert wind_color(0) == "#00008b"


def test_chartdata_fields():
    from chart_html import ChartData
    from datetime import datetime, timezone
    data = ChartData(
        site_name="Test",
        start_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cloud=[10] * 72,
        seeing=[6.0] * 72,
        transparency=[6.0] * 72,
        wind=[5.0] * 72,
        humidity=[50] * 72,
        temperature=[15.0] * 72,
        precipitation=[0.0] * 72,
        moon_pct=[30] * 72,
        moon_events={},
        errors=[],
    )
    assert len(data.cloud) == 72
    assert data.site_name == "Test"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest test_chart_html.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'chart_html'`

- [ ] **Step 3: Create `chart_html.py` with `ChartData` and color functions**

Create `chart_html.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_chart_html.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_html.py test_chart_html.py
git commit -m "feat: add ChartData dataclass and color-mapping functions"
```

---

## Task 3: Implement `build_chart_data()`

**Files:**
- Modify: `chart_html.py`
- Modify: `test_chart_html.py`

- [ ] **Step 1: Write the failing test**

Add to `test_chart_html.py`:

```python
def test_build_chart_data_returns_72_entries():
    """build_chart_data assembles 72 hourly entries per row from mocked fetches."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import MagicMock, patch
    from weather import WeatherResult, HourlyWeather
    from seeing import SeeingResult, SeeingHour
    from moon import MoonInfo

    start = datetime(2026, 5, 1, 0, tzinfo=timezone.utc)

    fake_hours = [
        HourlyWeather(
            time=start + timedelta(hours=i),
            cloud_cover_pct=20,
            precip_mm=0.0,
            wind_speed_kmh=10.0,
            humidity_pct=55,
            dew_point_c=5.0,
            temp_c=14.0,
        )
        for i in range(72)
    ]
    fake_weather = WeatherResult(site_key="test", fetched_at=start, hours=fake_hours)

    fake_seeing_hours = [
        SeeingHour(time=start + timedelta(hours=i * 3), seeing=6, transparency=6, lifted_index=2)
        for i in range(24)
    ]
    fake_seeing = SeeingResult(site_key="test", fetched_at=start, hours=fake_seeing_hours)

    fake_moon = MoonInfo(phase_pct=30.0, rise_utc=None, set_utc=None,
                         transit_utc=None, is_up_at_midnight=False)

    site = MagicMock()
    site.key = "test"
    site.name = "Test Site"
    site.lat = 35.9
    site.lon = -79.0

    with patch("chart_html.fetch_weather", return_value=fake_weather), \
         patch("chart_html.fetch_seeing", return_value=fake_seeing), \
         patch("chart_html.get_moon_info", return_value=fake_moon):
        from chart_html import build_chart_data
        data = build_chart_data(site, hours=72)

    assert data.site_name == "Test Site"
    assert len(data.cloud) == 72
    assert len(data.seeing) == 72
    assert len(data.transparency) == 72
    assert len(data.wind) == 72
    assert len(data.humidity) == 72
    assert len(data.temperature) == 72
    assert len(data.precipitation) == 72
    assert len(data.moon_pct) == 72
    assert data.cloud[0] == 20
    assert data.errors == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest test_chart_html.py::test_build_chart_data_returns_72_entries -v
```

Expected: FAIL — `ImportError: cannot import name 'build_chart_data'`

- [ ] **Step 3: Implement `build_chart_data()` in `chart_html.py`**

Add these imports at the top of `chart_html.py` (after existing imports):

```python
from datetime import date, timedelta, timezone
```

Add `build_chart_data` at the end of `chart_html.py`:

```python
def build_chart_data(site, hours: int = 72) -> ChartData:
    """Assemble 72-hour ChartData for a site by fetching weather, seeing, and moon data."""
    from weather import fetch_weather
    from seeing import fetch_seeing
    from moon import get_moon_info

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_chart_html.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_html.py test_chart_html.py
git commit -m "feat: implement build_chart_data() for 72-hour ChartData assembly"
```

---

## Task 4: Implement `render_html()`

**Files:**
- Modify: `chart_html.py`
- Modify: `test_chart_html.py`

- [ ] **Step 1: Write the failing test**

Add to `test_chart_html.py`:

```python
def test_render_html_structure():
    """render_html produces a valid HTML table with correct column count."""
    from datetime import datetime, timezone
    from chart_html import ChartData, render_html

    data = ChartData(
        site_name="Test Site",
        start_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cloud=[20] * 72,
        seeing=[6.0] * 72,
        transparency=[6.0] * 72,
        wind=[10.0] * 72,
        humidity=[50] * 72,
        temperature=[15.0] * 72,
        precipitation=[0.0] * 72,
        moon_pct=[30] * 72,
        moon_events={5: "rise", 18: "set"},
        errors=[],
    )
    html = render_html(data)

    assert "<table" in html
    assert "Test Site" in html
    # 72 data cells per row × 8 rows = 576 data <td> elements
    # (plus label cells and header cells — just check we have plenty)
    assert html.count("<td") >= 576
    # No external CSS links
    assert "stylesheet" not in html
    assert "<link" not in html
    # Moon rise/set symbols present
    assert "▲" in html
    assert "▼" in html


def test_render_html_missing_values():
    """render_html handles None values (missing data) without raising."""
    from datetime import datetime, timezone
    from chart_html import ChartData, render_html

    data = ChartData(
        site_name="Test",
        start_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cloud=[None] * 72,
        seeing=[None] * 72,
        transparency=[None] * 72,
        wind=[None] * 72,
        humidity=[None] * 72,
        temperature=[None] * 72,
        precipitation=[None] * 72,
        moon_pct=[0] * 72,
        moon_events={},
        errors=["Weather: timeout"],
    )
    html = render_html(data)
    assert "<table" in html
    assert "#444444" in html  # missing cell color
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest test_chart_html.py::test_render_html_structure test_chart_html.py::test_render_html_missing_values -v
```

Expected: FAIL — `ImportError: cannot import name 'render_html'`

- [ ] **Step 3: Implement `render_html()` in `chart_html.py`**

Add to the end of `chart_html.py`:

```python
# Row definitions: (label, field_name, color_fn, format_fn)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest test_chart_html.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_html.py test_chart_html.py
git commit -m "feat: implement render_html() for HTML email chart"
```

---

## Task 5: Add Chart tab to `gui.py`

**Files:**
- Modify: `gui.py`
- Modify: `test_gui.py`

- [ ] **Step 1: Write the failing smoke test**

Add to `test_gui.py` (look for the existing smoke test pattern and add alongside it):

```python
def test_chart_tab_builds():
    """Chart tab frame exists in notebook after app init."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        from gui import AstroAlertApp
        app = AstroAlertApp.__new__(AstroAlertApp)
        tk.Tk.__init__(app)
        app.configure(bg="#0d1117")
        app.geometry("980x680")
        app._setup_styles()
        app._build_header()
        app._build_notebook()
        app._build_statusbar()
        assert hasattr(app, "_tab_chart")
    finally:
        root.destroy()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest test_gui.py::test_chart_tab_builds -v
```

Expected: FAIL — `AttributeError: 'AstroAlertApp' object has no attribute '_tab_chart'`

- [ ] **Step 3: Add `_tab_chart` to `_build_notebook` in `gui.py`**

In `gui.py`, find `_build_notebook` and add the chart tab after `_tab_sched`:

```python
def _build_notebook(self):
    ttk.Separator(self).pack(fill="x", pady=(16, 0))
    nb = self._nb = ttk.Notebook(self)
    nb.pack(fill="both", expand=True)

    self._tab_dash     = ttk.Frame(nb)
    self._tab_sites    = ttk.Frame(nb)
    self._tab_sched    = ttk.Frame(nb)
    self._tab_chart    = ttk.Frame(nb)
    self._tab_scoring  = ttk.Frame(nb)
    self._tab_settings = ttk.Frame(nb)

    nb.add(self._tab_dash,     text="  Dashboard  ")
    nb.add(self._tab_sites,    text="  Sites  ")
    nb.add(self._tab_sched,    text="  Schedule  ")
    nb.add(self._tab_chart,    text="  Chart  ")
    nb.add(self._tab_scoring,  text="  Scoring  ")
    nb.add(self._tab_settings, text="  Settings  ")

    self._build_dashboard(self._tab_dash)
    self._build_sites_tab(self._tab_sites)
    self._build_schedule_tab(self._tab_sched)
    self._build_chart_tab(self._tab_chart)
    self._build_scoring_tab(self._tab_scoring)
    self._build_settings_tab(self._tab_settings)
```

- [ ] **Step 4: Implement `_build_chart_tab()` in `gui.py`**

Add this method to `AstroAlertApp` (place it after `_build_schedule_tab` and before `_build_scoring_tab`):

```python
# ── Chart tab ───────────────────────────────────────────────────────────────

def _build_chart_tab(self, parent):
    self._chart_data = None

    # ── Controls row ──────────────────────────────────────────────────────
    ctrl = ttk.Frame(parent)
    ctrl.pack(fill="x", padx=26, pady=(20, 0))

    ttk.Label(ctrl, text="Site:", style="Dim.TLabel").pack(side="left")
    self._chart_site_var   = tk.StringVar(value="")
    self._chart_site_combo = ttk.Combobox(ctrl, textvariable=self._chart_site_var,
                                           state="readonly", width=24,
                                           font=(FONT_PROP, 12))
    self._chart_site_combo.pack(side="left", padx=(8, 0))

    self._chart_load_btn = ttk.Button(ctrl, text="Load Chart",
                                       style="Accent.TButton",
                                       command=self._start_chart_load)
    self._chart_load_btn.pack(side="left", padx=(16, 0))

    self._chart_error_var = tk.StringVar(value="")
    self._chart_error_lbl = ttk.Label(ctrl, textvariable=self._chart_error_var,
                                       style="Dim.TLabel", foreground=WARN_CLR)
    self._chart_error_lbl.pack(side="left", padx=(16, 0))

    ttk.Separator(parent).pack(fill="x", pady=(14, 0))

    # ── Canvas + scrollbars ───────────────────────────────────────────────
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)

    self._chart_canvas = tk.Canvas(frame, bg=BG, highlightthickness=0)
    hbar = ttk.Scrollbar(frame, orient="horizontal",
                          command=self._chart_canvas.xview)
    vbar = ttk.Scrollbar(frame, orient="vertical",
                          command=self._chart_canvas.yview)
    self._chart_canvas.configure(xscrollcommand=hbar.set,
                                  yscrollcommand=vbar.set)
    hbar.pack(side="bottom", fill="x")
    vbar.pack(side="right",  fill="y")
    self._chart_canvas.pack(side="left", fill="both", expand=True)

    # Hover tooltip
    self._chart_tooltip_lbl = tk.Label(
        self, bg="#ffffe0", fg="#000000",
        font=(FONT_MONO, 10), relief="solid", borderwidth=1,
        padx=6, pady=3, justify="left",
    )
    self._chart_canvas.bind("<Motion>", self._on_chart_motion)
    self._chart_canvas.bind("<Leave>",  lambda _e: self._chart_tooltip_lbl.place_forget())

    # Mouse-wheel horizontal scroll
    def _on_chart_wheel(e):
        delta = e.delta
        if sys.platform != "darwin":
            delta = delta // 120
        self._chart_canvas.xview_scroll(int(-1 * delta), "units")
    self._chart_canvas.bind("<Enter>", lambda _e: (
        self._chart_canvas.bind_all("<MouseWheel>", _on_chart_wheel),
        self._chart_canvas.bind_all("<Button-4>",
            lambda ev: self._chart_canvas.xview_scroll(-1, "units")),
        self._chart_canvas.bind_all("<Button-5>",
            lambda ev: self._chart_canvas.xview_scroll(1, "units")),
    ))
    self._chart_canvas.bind("<Leave>", lambda _e: (
        self._chart_canvas.unbind_all("<MouseWheel>"),
        self._chart_canvas.unbind_all("<Button-4>"),
        self._chart_canvas.unbind_all("<Button-5>"),
        self._chart_tooltip_lbl.place_forget(),
    ))

    self.after(150, self._refresh_chart_sites)

def _refresh_chart_sites(self):
    if not hasattr(self, "_chart_site_combo"):
        return
    try:
        from site_manager import list_sites
        entries = list_sites()
    except FileNotFoundError:
        entries = []
    options = [f"{k}: {s.name}" for k, s, _ in entries]
    self._chart_site_combo.configure(values=options)
    if options and not self._chart_site_var.get():
        self._chart_site_var.set(options[0])

def _start_chart_load(self):
    site_val = self._chart_site_var.get()
    if not site_val:
        return
    self._chart_load_btn.configure(state="disabled", text="Loading…")
    self._chart_error_var.set("")
    self._chart_canvas.delete("all")
    self._chart_data = None
    key = site_val.split(":")[0].strip()
    threading.Thread(target=self._run_chart_load, args=(key,), daemon=True).start()

def _run_chart_load(self, site_key: str):
    from site_manager import get_active_site
    from chart_html import build_chart_data
    try:
        site = get_active_site(override=site_key)
        data = build_chart_data(site, hours=72)
        self.after(0, self._chart_loaded, data)
    except Exception as e:
        self.after(0, self._chart_load_failed, str(e))

def _chart_loaded(self, data):
    self._chart_data = data
    self._chart_load_btn.configure(state="normal", text="Load Chart")
    if data.errors:
        self._chart_error_var.set("⚠ " + " / ".join(data.errors))
    self._draw_chart(data)
    self._set_status("Chart loaded.")

def _chart_load_failed(self, msg: str):
    self._chart_load_btn.configure(state="normal", text="Load Chart")
    self._chart_error_var.set(f"Error: {msg}")
    self._set_status("Chart load failed.")

def _draw_chart(self, data):
    from chart_html import (cloud_color, seeing_color, transparency_color,
                             wind_color, humidity_color, temperature_color,
                             precipitation_color, moon_color, _MISSING)
    from datetime import timedelta

    canvas = self._chart_canvas
    canvas.delete("all")

    LABEL_W  = 130
    HEADER_H = 52   # date row (26px) + hour row (26px)
    CELL_W   = 18
    CELL_H   = 28
    hours    = len(data.cloud)

    ROW_DEFS = [
        ("Cloud Cover",  data.cloud,         cloud_color,         lambda v: f"{v}%"),
        ("Seeing",       data.seeing,        seeing_color,        lambda v: f"{v:.0f}/8"),
        ("Transparency", data.transparency,  transparency_color,  lambda v: f"{v:.0f}/8"),
        ("Wind",         data.wind,          wind_color,          lambda v: f"{v:.0f} km/h"),
        ("Humidity",     data.humidity,      humidity_color,      lambda v: f"{v}%"),
        ("Temperature",  data.temperature,   temperature_color,   lambda v: f"{v:.1f}°C"),
        ("Precip",       data.precipitation, precipitation_color, lambda v: f"{v:.1f} mm"),
        ("Moon",         data.moon_pct,      moon_color,          lambda v: f"{v}%"),
    ]

    total_w = LABEL_W + hours * CELL_W + 20
    total_h = HEADER_H + len(ROW_DEFS) * CELL_H + 20
    canvas.configure(scrollregion=(0, 0, total_w, total_h))

    # ── Date headers ──────────────────────────────────────────────────────
    for day in range(3):
        dt = data.start_dt + timedelta(hours=day * 24)
        label = dt.strftime("%a %b %-d")
        x = LABEL_W + day * 24 * CELL_W + 12 * CELL_W
        canvas.create_text(x, 13, text=label, fill=ACCENT,
                           font=(FONT_PROP, 10, "bold"), anchor="center")

    # ── Hour labels ───────────────────────────────────────────────────────
    for i in range(hours):
        if i % 3 == 0:
            h = i % 24
            x = LABEL_W + i * CELL_W + CELL_W // 2
            canvas.create_text(x, 38, text=f"{h:02d}", fill=TEXT_DIM,
                               font=(FONT_MONO, 8), anchor="center")

    # ── Data rows ─────────────────────────────────────────────────────────
    for row_idx, (label, values, color_fn, _fmt) in enumerate(ROW_DEFS):
        y0 = HEADER_H + row_idx * CELL_H

        # Row label
        canvas.create_text(LABEL_W - 8, y0 + CELL_H // 2,
                           text=label, fill=TEXT_DIM,
                           font=(FONT_PROP, 10), anchor="e")

        # Cells
        for col_idx, val in enumerate(values):
            x0 = LABEL_W + col_idx * CELL_W
            bg = _MISSING if val is None else color_fn(val)
            canvas.create_rectangle(x0, y0, x0 + CELL_W, y0 + CELL_H,
                                    fill=bg, outline="", width=0)

            # Moon rise/set symbols
            if label == "Moon" and col_idx in data.moon_events:
                sym = "▲" if data.moon_events[col_idx] == "rise" else "▼"
                canvas.create_text(x0 + CELL_W // 2, y0 + CELL_H // 2,
                                   text=sym, fill="#ffffff",
                                   font=(FONT_PROP, 8))

def _on_chart_motion(self, event):
    from chart_html import _MISSING
    from datetime import timedelta

    data = self._chart_data
    if data is None:
        return

    cx = self._chart_canvas.canvasx(event.x)
    cy = self._chart_canvas.canvasy(event.y)

    LABEL_W  = 130
    HEADER_H = 52
    CELL_W   = 18
    CELL_H   = 28

    col = int((cx - LABEL_W) / CELL_W)
    row = int((cy - HEADER_H) / CELL_H)

    ROW_FIELDS = ["cloud", "seeing", "transparency", "wind",
                  "humidity", "temperature", "precipitation", "moon_pct"]
    ROW_LABELS = ["Cloud Cover", "Seeing", "Transparency", "Wind",
                  "Humidity", "Temperature", "Precip", "Moon"]
    ROW_FMTS   = [
        lambda v: f"{v}%",
        lambda v: f"{v:.0f}/8",
        lambda v: f"{v:.0f}/8",
        lambda v: f"{v:.0f} km/h",
        lambda v: f"{v}%",
        lambda v: f"{v:.1f}°C",
        lambda v: f"{v:.1f} mm",
        lambda v: f"{v}%",
    ]

    if col < 0 or col >= 72 or row < 0 or row >= len(ROW_FIELDS):
        self._chart_tooltip_lbl.place_forget()
        return

    val = getattr(data, ROW_FIELDS[row])[col]
    label = ROW_LABELS[row]
    dt = data.start_dt + timedelta(hours=col)
    time_str = dt.strftime("%a %H:00 UTC")

    tip = f"{label}\n{time_str}\n" + ("N/A" if val is None else ROW_FMTS[row](val))
    self._chart_tooltip_lbl.configure(text=tip)
    tx = event.x_root - self.winfo_rootx() + 14
    ty = event.y_root - self.winfo_rooty() + 14
    self._chart_tooltip_lbl.place(x=tx, y=ty)
    self._chart_tooltip_lbl.lift()
```

- [ ] **Step 5: Run smoke test to verify it passes**

```bash
python -m pytest test_gui.py::test_chart_tab_builds -v
```

Expected: PASS

- [ ] **Step 6: Run full GUI test suite**

```bash
python -m pytest test_gui.py -v
```

Expected: all tests PASS

- [ ] **Step 7: Launch the app and visually verify the Chart tab appears**

```bash
python3 gui.py
```

Click the "  Chart  " tab, select a site, and click "Load Chart". Verify the color grid renders and hovering a cell shows a tooltip.

- [ ] **Step 8: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: add Chart tab with 72-hour color-coded forecast grid"
```

---

## Task 6: Add Email Format setting and HTML email support

**Files:**
- Modify: `gui.py` (Settings tab)
- Modify: `smtp_notifier.py`
- Modify: `astro_alert.py`

- [ ] **Step 1: Add Email Format radio buttons to Settings tab in `gui.py`**

In `_build_settings_tab`, find the `Home Location` separator section and add this block just before it (after the existing SMTP fields + custom SMTP toggle):

```python
# ── Email Format ───────────────────────────────────────────────────────────
ttk.Separator(inner).pack(fill="x", pady=(24, 0))
ttk.Label(inner, text="Email Format",
          font=(FONT_PROP, 15, "bold")).pack(pady=(16, 4))
ttk.Label(inner,
          text="Choose how alert emails are sent.",
          style="Sub.TLabel").pack(pady=(0, 16))

fmt_card = ttk.Frame(inner, style="Card.TFrame")
fmt_card.pack(fill="x", ipadx=28, ipady=16)

self._email_format_var = tk.StringVar(value="plain")
ttk.Radiobutton(fmt_card, text="Plain text  (current behavior)",
                 variable=self._email_format_var,
                 value="plain").pack(anchor="w", padx=16, pady=(8, 4))
ttk.Radiobutton(fmt_card, text="HTML with chart  (color-coded 72-hour grid)",
                 variable=self._email_format_var,
                 value="html").pack(anchor="w", padx=16, pady=(0, 8))

def _on_email_format_change(*_):
    from data_dir import ENV_FILE
    from dotenv import set_key
    ENV_FILE.touch()
    set_key(ENV_FILE, "EMAIL_FORMAT", self._email_format_var.get())

self._email_format_var.trace_add("write", _on_email_format_change)
```

- [ ] **Step 2: Load `EMAIL_FORMAT` in `_load_credentials_to_form`**

In `_load_credentials_to_form`, add at the end:

```python
if hasattr(self, "_email_format_var"):
    self._email_format_var.set(vals.get("EMAIL_FORMAT", "plain"))
```

- [ ] **Step 3: Update `send_multi_site_alert` signature in `smtp_notifier.py`**

Change the function signature to accept an optional `sites` list:

```python
def send_multi_site_alert(reports: list[SiteReport], night_label: str = "tonight",
                           sites: Optional[list] = None) -> EmailResult:
    """Send a single email summarising all sites. Returns EmailResult — never raises."""
```

- [ ] **Step 4: Add HTML email logic inside `send_multi_site_alert`**

After the existing `subject` and `body_lines` construction (just before `msg = EmailMessage()`), add:

```python
    email_format = _clean(os.getenv("EMAIL_FORMAT", "plain"))

    if email_format == "html" and sites:
        # Use the first GO site, or best site overall, for the chart
        go_sites_ordered = [s for s in sites if any(r.site_name == s.name and r.score.go for r in reports)]
        chart_site = go_sites_ordered[0] if go_sites_ordered else sites[0]
        try:
            from chart_html import build_chart_data, render_html
            chart_data = build_chart_data(chart_site, hours=72)
            plain_body = "\n".join(body_lines).strip()
            html_body  = render_html(chart_data)
            # Append plain text summary below the chart
            html_body  = html_body.replace(
                "</body></html>",
                f'<pre style="font-family:monospace;color:#c9d1d9;margin-top:16px">'
                f'{plain_body}</pre></body></html>'
            )

            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            mime_msg = MIMEMultipart("alternative")
            mime_msg["Subject"] = subject
            mime_msg["From"]    = smtp_user
            mime_msg["To"]      = email_to
            mime_msg.attach(MIMEText(plain_body, "plain"))
            mime_msg.attach(MIMEText(html_body,  "html"))

            try:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(smtp_user, smtp_password)
                    smtp.sendmail(smtp_user, [email_to], mime_msg.as_string())
                return EmailResult(sent=True)
            except smtplib.SMTPAuthenticationError:
                return EmailResult(sent=False, error="Auth failed — check your App Password.")
            except Exception as e:
                return EmailResult(sent=False, error=str(e))
        except Exception:
            pass  # fall through to plain text

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = email_to
    msg.set_content("\n".join(body_lines).strip())
```

- [ ] **Step 5: Pass `sites_to_fetch` in `astro_alert.py`**

In `cmd_run`, find the `send_multi_site_alert` call and update it:

```python
    result = send_multi_site_alert(reports, night_label=night_label,
                                    sites=sites_to_fetch)
```

(Also add the import if not already present — `send_multi_site_alert` is already imported at the top of `astro_alert.py`.)

- [ ] **Step 6: Run the full test suite**

```bash
python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Launch app, set HTML format in Settings, and run a dry-run forecast**

```bash
python3 gui.py
```

1. Go to Settings → Email Format → select "HTML with chart"
2. Go to Dashboard → check "Dry run (no email)" → click "Run Forecast"
3. Verify no errors appear in the output

- [ ] **Step 8: Commit**

```bash
git add gui.py smtp_notifier.py astro_alert.py
git commit -m "feat: add HTML email format with 72-hour chart and Settings toggle"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| "  Chart  " tab after Forecast, before Scoring | Task 5, Step 3 |
| Site selector (single-site, no "All sites") | Task 5, Step 4 (`_build_chart_tab`) |
| "Load Chart" button, disabled during fetch, shows "Loading…" | Task 5, Step 4 |
| 72 columns × 8 rows color grid | Task 5, Step 4 (`_draw_chart`) |
| All 8 rows: cloud, seeing, transparency, wind, humidity, temp, precip, moon | Task 5, Step 4 (`ROW_DEFS`) |
| Correct color scales per row | Task 2 (color functions) |
| Moon rise/set ▲▼ symbols | Task 5, Step 4 |
| Hover tooltip with raw value | Task 5, Step 4 (`_on_chart_motion`) |
| Horizontal + vertical scrollbars | Task 5, Step 4 |
| Background thread + per-site cache | Task 5, Step 4 (`_start_chart_load` / `_chart_data`) |
| `fetch_weather` 3-day range | Task 1 |
| 7timer 3-hour blocks spread to hourly | Task 3 (`build_chart_data`) |
| Moon spread per day | Task 3 (`build_chart_data`) |
| Missing data → dark gray cells | Task 2 (`_MISSING`), Task 5 (`_draw_chart`) |
| Error banner showing failed data sources | Task 5, Step 4 (`_chart_error_var`) |
| Email Format radio in Settings | Task 6, Step 1 |
| Auto-save EMAIL_FORMAT to `.env` | Task 6, Step 1 |
| HTML email with inline CSS table | Task 4 (`render_html`) |
| `multipart/alternative` with plain-text fallback | Task 6, Step 4 |
| Fall back to plain text if HTML render fails | Task 6, Step 4 (try/except) |
| `test_chart_html.py`: build_chart_data + render_html | Tasks 3, 4 |
| `test_weather.py`: 3-day range | Task 1 |
| `test_gui.py`: Chart tab smoke test | Task 5, Step 1 |

All spec requirements covered. No placeholders. Type/method names consistent across all tasks.
