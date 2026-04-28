import json
from datetime import datetime, timezone
from pathlib import Path

from target_recommender import get_nightly_targets, TargetResult

LAT, LON = 36.0, -78.9   # Durham NC
UTC = timezone.utc


def test_targets_json_loads_and_has_required_fields():
    data = json.loads((Path(__file__).parent / "targets.json").read_text())
    assert len(data) >= 90
    required = {"name", "common_name", "type", "ra", "dec", "magnitude", "size_arcmin", "description"}
    for entry in data:
        missing = required - entry.keys()
        assert not missing, f"{entry.get('name', '?')} missing: {missing}"


def _window(start_hour, end_hour, year=2024, month=6, day=15):
    return {
        datetime(year, month, day, h, tzinfo=UTC)
        for h in range(start_hour, end_hour + 1)
    }


def test_returns_empty_on_empty_window():
    results = get_nightly_targets(LAT, LON, set())
    assert results == []


def test_returns_empty_on_missing_targets_file(tmp_path, monkeypatch):
    monkeypatch.setattr("target_recommender._TARGETS_FILE", tmp_path / "missing.json")
    results = get_nightly_targets(LAT, LON, _window(0, 10))
    assert results == []


def test_m13_visible_in_june_from_north_carolina():
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window)
    names = [r.name for r in results]
    assert "M13" in names


def test_filters_target_below_min_alt():
    window = {datetime(2024, 1, 1, 12, tzinfo=UTC)}
    results = get_nightly_targets(LAT, LON, window, min_alt_deg=25.0, min_hours=1.0)
    for r in results:
        assert r.peak_alt_deg >= 25.0


def test_sorts_by_peak_altitude_descending():
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=10)
    alts = [r.peak_alt_deg for r in results]
    assert alts == sorted(alts, reverse=True)


def test_respects_max_results():
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=3)
    assert len(results) <= 3


def test_transit_utc_is_hour_of_peak_altitude():
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=5)
    for r in results:
        assert r.transit_utc is not None
        assert r.transit_utc in window
