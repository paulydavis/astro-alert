"""Tests for scorer.py."""

from datetime import date, datetime, timezone
import pytest

from moon import MoonInfo
from scorer import score_night, _weather_score, _seeing_score, _moon_score, _dark_hours_after_moonset, _imaging_hours
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


def moonset_at(hour: float):
    """Return a UTC datetime with the given decimal hour (e.g. 22.5 = 22:30)."""
    h = int(hour)
    m = int((hour - h) * 60)
    # Use next-day date for early-morning hours (00–04 window)
    d = 2 if h < 12 else 1
    return datetime(2024, 1, d, h, m, tzinfo=timezone.utc)


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


# --- dark hours after moonset ------------------------------------------------

class TestDarkHoursAfterMoonset:
    def test_no_set_utc(self):
        moon = make_moon(phase=80)
        assert _dark_hours_after_moonset(moon) == 0.0

    def test_sets_before_imaging_window(self):
        # Sets at 18:00 — well before 20:00 start
        moon = make_moon(set_=moonset_at(18))
        assert _dark_hours_after_moonset(moon) == 8.0

    def test_sets_exactly_at_window_start(self):
        moon = make_moon(set_=moonset_at(20))
        assert _dark_hours_after_moonset(moon) == 8.0

    def test_sets_at_midnight(self):
        # Midnight = hour 24 in normalized space; imaging_end=28, so 28-24=4 dark hrs
        moon = make_moon(set_=moonset_at(0))  # 00:00 UTC next day
        assert abs(_dark_hours_after_moonset(moon) - 4.0) < 0.1

    def test_sets_at_22(self):
        moon = make_moon(set_=moonset_at(22))
        assert abs(_dark_hours_after_moonset(moon) - 6.0) < 0.1

    def test_sets_after_imaging_window(self):
        # Sets at 05:00 — after 04:00 end
        moon = make_moon(set_=moonset_at(5))
        assert _dark_hours_after_moonset(moon) == 0.0


# --- moon scoring ------------------------------------------------------------

class TestMoonScore:
    def test_new_moon(self):
        pts, warns = _moon_score(make_moon(phase=5))
        assert pts == 30
        assert not warns

    def test_full_moon_no_set(self):
        # ≥75%, no moonset info → 0 pts
        pts, warns = _moon_score(make_moon(phase=99))
        assert pts == 0
        assert warns

    def test_full_moon_sets_before_midnight(self):
        # ≥75% but sets at 22:00 — 6 dark hours → some credit
        moon = make_moon(phase=99, is_up=False, set_=moonset_at(22))
        pts, warns = _moon_score(moon)
        assert pts > 0
        assert any("sets" in w for w in warns)

    def test_full_moon_sets_after_imaging(self):
        # ≥75%, sets at 05:00 — after window ends → 0 pts
        moon = make_moon(phase=99, is_up=True, set_=moonset_at(5))
        pts, warns = _moon_score(moon)
        assert pts == 0

    def test_bright_moon_early_set_more_pts_than_late_set(self):
        early = make_moon(phase=80, set_=moonset_at(21))
        late = make_moon(phase=80, set_=moonset_at(23))
        pts_early, _ = _moon_score(early)
        pts_late, _ = _moon_score(late)
        assert pts_early > pts_late

    def test_moon_up_at_midnight_penalty(self):
        # Only applies for phase < 75
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

    def test_bright_moon_up_at_midnight_hard_nogo(self):
        # ≥75% + up at midnight = hard NO-GO even with perfect weather/seeing
        score = score_night(
            make_weather(cloud=0),
            make_seeing(8, 8),
            make_moon(phase=80, is_up=True),
            bortle=7,
        )
        assert not score.go
        assert "bright moon" in score.summary.lower()

    def test_bright_moon_sets_before_midnight_not_hard_nogo(self):
        # ≥75% but NOT up at midnight — hard cutoff should not apply
        score = score_night(
            make_weather(cloud=0),
            make_seeing(8, 8),
            make_moon(phase=80, is_up=False, set_=moonset_at(21)),
            bortle=7,
        )
        # Should be evaluated on score, not hard-blocked
        assert "bright moon" not in score.summary.lower()

    def test_summary_excellent(self):
        score = score_night(
            make_weather(cloud=5, wind=3),
            make_seeing(8, 8),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go
        assert "excellent" in score.summary.lower()

    def test_summary_good(self):
        # Need total 65–79: clear sky (40) + mid seeing (15+10=25) + new moon (30) = 95 — too high.
        # Use partly cloudy (18) + mid seeing (22) + new moon (30) = 70
        score = score_night(
            make_weather(cloud=30),
            make_seeing(6, 6),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go
        assert "good" in score.summary.lower()

    def test_summary_marginal(self):
        # cloud=20 → 32pts, seeing(3,3) → 10pts, quarter moon(40%) → 15pts = 57 (marginal 55–64)
        score = score_night(
            make_weather(cloud=20),
            make_seeing(3, 3),
            make_moon(phase=40),
            bortle=7,
        )
        assert score.go
        assert "marginal" in score.summary.lower()

    def test_target_date_filters_hours(self):
        # Hours outside the imaging window for target_date should be ignored
        target = date(2024, 1, 1)
        # Hour 21 on target_date IS in window; hour 10 is NOT
        h_in = HourlyWeather(
            time=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            cloud_cover_pct=0, precip_mm=0, wind_speed_kmh=5,
            humidity_pct=50, dew_point_c=5, temp_c=15,
        )
        h_out = HourlyWeather(
            time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            cloud_cover_pct=100, precip_mm=5, wind_speed_kmh=50,
            humidity_pct=99, dew_point_c=14, temp_c=15,
        )
        result = WeatherResult(
            site_key="test",
            fetched_at=datetime.now(timezone.utc),
            hours=[h_in, h_out],
        )
        pts_with_date, _ = _weather_score(result, bortle=7, target_date=target)
        pts_no_date, _ = _weather_score(result, bortle=7, target_date=None)
        # With date filtering only the clear hour counts — score should be higher
        assert pts_with_date > pts_no_date

    def test_moderate_wind_penalty(self):
        pts_calm, _ = _weather_score(make_weather(wind=5), bortle=7)
        pts_moderate, warns = _weather_score(make_weather(wind=25), bortle=7)
        assert pts_moderate < pts_calm
        assert any("moderate wind" in w.lower() for w in warns)

    def test_high_humidity_warning(self):
        _, warns = _weather_score(make_weather(humidity=95, dew_gap=5), bortle=7)
        assert any("humidity" in w.lower() for w in warns)


# --- _imaging_hours ----------------------------------------------------------

class TestImagingHours:
    def test_returns_nine_hours(self):
        # 20,21,22,23 + 00,01,02,03,04 = 9 hours
        hours = _imaging_hours(date(2024, 6, 15))
        assert len(hours) == 9

    def test_evening_hours_on_target_date(self):
        target = date(2024, 6, 15)
        hours = _imaging_hours(target)
        assert datetime(2024, 6, 15, 21, tzinfo=timezone.utc) in hours

    def test_early_morning_on_next_date(self):
        target = date(2024, 6, 15)
        hours = _imaging_hours(target)
        assert datetime(2024, 6, 16, 2, tzinfo=timezone.utc) in hours

    def test_midday_not_in_window(self):
        target = date(2024, 6, 15)
        hours = _imaging_hours(target)
        assert datetime(2024, 6, 15, 12, tzinfo=timezone.utc) not in hours
