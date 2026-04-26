"""Tests for scorer.py."""

from datetime import datetime, timezone
import pytest

from moon import MoonInfo
from scorer import score_night, _weather_score, _seeing_score, _moon_score
from seeing import SeeingResult, SeeingHour
from weather import WeatherResult, HourlyWeather


def make_weather(cloud=5, precip=0.0, wind=5.0, humidity=50, dew_gap=8.0, error=None):
    if error:
        return WeatherResult(site_key="test", fetched_at=datetime.now(timezone.utc), hours=[], error=error)
    h = HourlyWeather(
        time=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
        cloud_cover_pct=cloud,
        precip_mm=precip,
        wind_speed_kmh=wind,
        humidity_pct=humidity,
        dew_point_c=10.0,
        temp_c=10.0 + dew_gap,
    )
    return WeatherResult(site_key="test", fetched_at=datetime.now(timezone.utc), hours=[h])


def make_seeing(seeing=6, transparency=6, error=None):
    if error:
        return SeeingResult(site_key="test", fetched_at=datetime.now(timezone.utc), hours=[], error=error)
    h = SeeingHour(
        time=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
        seeing=seeing,
        transparency=transparency,
        lifted_index=2,
    )
    return SeeingResult(site_key="test", fetched_at=datetime.now(timezone.utc), hours=[h])


def make_moon(phase=5.0, is_up=False, rise=None, set_=None):
    return MoonInfo(
        phase_pct=phase,
        rise_utc=rise,
        set_utc=set_,
        transit_utc=None,
        is_up_at_midnight=is_up,
    )


# --- weather scoring ---------------------------------------------------------

class TestWeatherScore:
    def test_clear_sky(self):
        pts, warns = _weather_score(make_weather(cloud=5), bortle=7)
        assert pts == 40
        assert not warns

    def test_partly_cloudy(self):
        pts, warns = _weather_score(make_weather(cloud=30), bortle=7)
        assert pts < 40
        assert any("cloudy" in w.lower() for w in warns)

    def test_overcast(self):
        pts, warns = _weather_score(make_weather(cloud=90), bortle=7)
        assert pts == 0

    def test_precipitation_zeroes_score(self):
        pts, warns = _weather_score(make_weather(cloud=5, precip=1.0), bortle=7)
        assert pts == 0
        assert any("precip" in w.lower() for w in warns)

    def test_dark_site_cloud_weight(self):
        pts_dark, _ = _weather_score(make_weather(cloud=20), bortle=3)
        pts_bright, _ = _weather_score(make_weather(cloud=20), bortle=7)
        assert pts_dark >= pts_bright  # dark site rewards clearer sky more

    def test_high_wind_penalty(self):
        pts_calm, _ = _weather_score(make_weather(wind=5), bortle=7)
        pts_windy, warns = _weather_score(make_weather(wind=35), bortle=7)
        assert pts_windy < pts_calm
        assert any("wind" in w.lower() for w in warns)

    def test_dew_risk_warning(self):
        _, warns = _weather_score(make_weather(dew_gap=1), bortle=7)
        assert any("dew" in w.lower() for w in warns)

    def test_unavailable_data_returns_neutral(self):
        pts, warns = _weather_score(make_weather(error="timeout"), bortle=7)
        assert pts == 20
        assert any("unavailable" in w.lower() for w in warns)


# --- seeing scoring ----------------------------------------------------------

class TestSeeingScore:
    def test_excellent_seeing(self):
        pts, warns = _seeing_score(make_seeing(seeing=8, transparency=8))
        assert pts == 30
        assert not warns

    def test_poor_seeing_warning(self):
        pts, warns = _seeing_score(make_seeing(seeing=2, transparency=6))
        assert any("seeing" in w.lower() for w in warns)

    def test_poor_transparency_warning(self):
        _, warns = _seeing_score(make_seeing(seeing=6, transparency=2))
        assert any("transparency" in w.lower() for w in warns)

    def test_unavailable_returns_neutral(self):
        pts, warns = _seeing_score(make_seeing(error="timeout"))
        assert pts == 15
        assert any("unavailable" in w.lower() for w in warns)


# --- moon scoring ------------------------------------------------------------

class TestMoonScore:
    def test_new_moon(self):
        pts, warns = _moon_score(make_moon(phase=5))
        assert pts == 30
        assert not warns

    def test_full_moon(self):
        pts, warns = _moon_score(make_moon(phase=99))
        assert pts == 0
        assert warns

    def test_moon_up_at_midnight_penalty(self):
        pts_up, _ = _moon_score(make_moon(phase=30, is_up=True))
        pts_down, _ = _moon_score(make_moon(phase=30, is_up=False))
        assert pts_up < pts_down


# --- integrated score_night --------------------------------------------------

class TestScoreNight:
    def test_perfect_conditions_go(self):
        score = score_night(
            make_weather(cloud=5, wind=5),
            make_seeing(8, 8),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go
        assert score.total >= 80

    def test_terrible_conditions_nogo(self):
        score = score_night(
            make_weather(cloud=95, precip=2.0),
            make_seeing(1, 1),
            make_moon(phase=98, is_up=True),
            bortle=7,
        )
        assert not score.go
        assert score.total < 55

    def test_score_components_sum(self):
        score = score_night(
            make_weather(cloud=5),
            make_seeing(6, 6),
            make_moon(phase=10),
            bortle=7,
        )
        assert score.total == score.weather_score + score.seeing_score + score.moon_score

    def test_custom_threshold(self):
        score = score_night(
            make_weather(cloud=40),
            make_seeing(5, 5),
            make_moon(phase=40),
            bortle=7,
            go_threshold=10,
        )
        assert score.go
