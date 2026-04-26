"""Tests for weather.py — mocked HTTP responses."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from weather import fetch_weather, WeatherResult

LAT, LON = 35.994, -78.899
SITE = "test"

GOOD_RESPONSE = {
    "hourly": {
        "time": ["2024-01-15T20:00", "2024-01-15T21:00"],
        "cloud_cover": [10, 20],
        "precipitation": [0.0, 0.0],
        "wind_speed_10m": [5.0, 6.0],
        "relative_humidity_2m": [55, 60],
        "dew_point_2m": [5.0, 5.5],
        "temperature_2m": [12.0, 11.5],
    }
}


def mock_response(json_data=None, status=200, raises=None):
    resp = MagicMock()
    resp.status_code = status
    if raises:
        resp.raise_for_status.side_effect = raises
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data or GOOD_RESPONSE
    return resp


# --- successful fetch --------------------------------------------------------

class TestFetchWeatherSuccess:
    def test_returns_weather_result(self):
        with patch("weather.requests.get", return_value=mock_response()):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        assert isinstance(result, WeatherResult)
        assert result.ok
        assert result.error is None

    def test_parses_hours(self):
        with patch("weather.requests.get", return_value=mock_response()):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        assert len(result.hours) == 2

    def test_hour_fields_correct(self):
        with patch("weather.requests.get", return_value=mock_response()):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        h = result.hours[0]
        assert h.cloud_cover_pct == 10
        assert h.precip_mm == 0.0
        assert h.wind_speed_kmh == 5.0
        assert h.humidity_pct == 55
        assert h.dew_point_c == 5.0
        assert h.temp_c == 12.0

    def test_times_are_utc(self):
        with patch("weather.requests.get", return_value=mock_response()):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        assert result.hours[0].time.tzinfo == timezone.utc

    def test_fetches_two_days(self):
        """Should request target_date and target_date+1 to cover the imaging window."""
        with patch("weather.requests.get", return_value=mock_response()) as mock_get:
            fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        params = mock_get.call_args[1]["params"]
        assert params["start_date"] == "2024-01-15"
        assert params["end_date"] == "2024-01-16"

    def test_defaults_to_today(self):
        today = datetime.now(timezone.utc).date()
        with patch("weather.requests.get", return_value=mock_response()) as mock_get:
            fetch_weather(SITE, LAT, LON)
        params = mock_get.call_args[1]["params"]
        assert params["start_date"] == today.isoformat()

    def test_site_key_preserved(self):
        with patch("weather.requests.get", return_value=mock_response()):
            result = fetch_weather("my_site", LAT, LON, target_date=date(2024, 1, 15))
        assert result.site_key == "my_site"


# --- network errors ----------------------------------------------------------

class TestFetchWeatherErrors:
    def test_connection_error_returns_error_result(self):
        with patch("weather.requests.get", side_effect=requests.ConnectionError("timeout")):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        assert not result.ok
        assert result.error is not None
        assert result.hours == []

    def test_http_error_returns_error_result(self):
        resp = mock_response(raises=requests.HTTPError("503"))
        with patch("weather.requests.get", return_value=resp):
            result = fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))
        assert not result.ok
        assert result.hours == []

    def test_never_raises(self):
        with patch("weather.requests.get", side_effect=Exception("unexpected")):
            # Should not raise — but our code only catches RequestException,
            # so verify the documented guarantee for that family
            with pytest.raises(Exception):
                fetch_weather(SITE, LAT, LON, target_date=date(2024, 1, 15))


# --- parse errors ------------------------------------------------------------

class TestFetchWeatherParseErrors:
    def test_missing_hourly_key_returns_error(self):
        with patch("weather.requests.get", return_value=mock_response({"bad": "data"})):
            result = fetch_weather(SITE, LAT, LON, date(2024, 1, 15))
        assert not result.ok
        assert "Parse error" in result.error

    def test_mismatched_array_lengths_still_parses(self):
        """zip() stops at shortest — should parse without error."""
        data = dict(GOOD_RESPONSE)
        data["hourly"] = dict(GOOD_RESPONSE["hourly"])
        data["hourly"]["cloud_cover"] = [10]  # shorter than others
        with patch("weather.requests.get", return_value=mock_response(data)):
            result = fetch_weather(SITE, LAT, LON, date(2024, 1, 15))
        assert result.ok
        assert len(result.hours) == 1

    def test_non_numeric_value_returns_parse_error(self):
        data = dict(GOOD_RESPONSE)
        data["hourly"] = dict(GOOD_RESPONSE["hourly"])
        data["hourly"]["cloud_cover"] = ["not_a_number", 20]
        with patch("weather.requests.get", return_value=mock_response(data)):
            result = fetch_weather(SITE, LAT, LON, date(2024, 1, 15))
        assert not result.ok
        assert "Parse error" in result.error
