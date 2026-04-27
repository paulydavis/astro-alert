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


def test_build_chart_data_returns_72_entries():
    """build_chart_data assembles 72 hourly entries per row from mocked fetches."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import MagicMock, patch
    from weather import WeatherResult, HourlyWeather
    from seeing import SeeingResult, SeeingHour
    from moon import MoonInfo
    import chart_html

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

    # Patch datetime in the chart_html module namespace
    import sys
    from unittest.mock import MagicMock

    with patch("chart_html.fetch_weather", return_value=fake_weather), \
         patch("chart_html.fetch_seeing", return_value=fake_seeing), \
         patch("chart_html.get_moon_info", return_value=fake_moon):
        # Create a mock datetime class that preserves constructor but mocks now()
        mock_datetime_cls = MagicMock(wraps=datetime)
        mock_datetime_cls.now = staticmethod(lambda tz=None: start)

        with patch.dict(sys.modules['chart_html'].__dict__, {'datetime': mock_datetime_cls}):
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
    assert html.count("<td") >= 576
    assert "stylesheet" not in html
    assert "<link" not in html
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
