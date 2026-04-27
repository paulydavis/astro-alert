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
