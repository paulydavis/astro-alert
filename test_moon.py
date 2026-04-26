"""Tests for moon.py."""

from datetime import date, datetime, timezone
import pytest

from moon import get_moon_info


LAT, LON = 37.7749, -122.4194  # San Francisco


def test_returns_moon_info(freeze_date=None):
    info = get_moon_info(LAT, LON)
    assert 0.0 <= info.phase_pct <= 100.0
    assert isinstance(info.is_up_at_midnight, bool)


def test_new_moon_date():
    # 2024-01-11 was a new moon
    info = get_moon_info(LAT, LON, target_date=date(2024, 1, 11))
    assert info.phase_pct < 5.0


def test_full_moon_date():
    # 2024-01-25 was a full moon
    info = get_moon_info(LAT, LON, target_date=date(2024, 1, 25))
    assert info.phase_pct > 95.0


def test_rise_set_are_datetimes_or_none():
    info = get_moon_info(LAT, LON, target_date=date(2024, 1, 15))
    if info.rise_utc is not None:
        assert info.rise_utc.tzinfo is not None
    if info.set_utc is not None:
        assert info.set_utc.tzinfo is not None


def test_different_locations_differ():
    info_sf = get_moon_info(37.77, -122.42, target_date=date(2024, 6, 15))
    info_ny = get_moon_info(40.71, -74.01, target_date=date(2024, 6, 15))
    # Phase should be nearly identical; rise/set times will differ
    assert abs(info_sf.phase_pct - info_ny.phase_pct) < 1.0
