"""Tests for seeing.py — mocked HTTP responses."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from seeing import fetch_seeing, SeeingResult

LAT, LON = 35.994, -78.899
SITE = "test"

GOOD_RESPONSE = {
    "init": "2024011518",
    "dataseries": [
        {"timepoint": 3,  "seeing": 6, "transparency": 5, "lifted_index": 2},
        {"timepoint": 6,  "seeing": 7, "transparency": 6, "lifted_index": 3},
        {"timepoint": 9,  "seeing": 5, "transparency": 4, "lifted_index": 1},
    ],
}


def mock_response(json_data=None, raises=None):
    resp = MagicMock()
    if raises:
        resp.raise_for_status.side_effect = raises
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data or GOOD_RESPONSE
    return resp


# --- successful fetch --------------------------------------------------------

class TestFetchSeeingSuccess:
    def test_returns_seeing_result(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing(SITE, LAT, LON)
        assert isinstance(result, SeeingResult)
        assert result.ok
        assert result.error is None

    def test_parses_all_dataseries_entries(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing(SITE, LAT, LON)
        assert len(result.hours) == 3

    def test_hour_fields_correct(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing(SITE, LAT, LON)
        h = result.hours[0]
        assert h.seeing == 6
        assert h.transparency == 5
        assert h.lifted_index == 2

    def test_times_computed_from_init_and_offset(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing(SITE, LAT, LON)
        # init = 2024-01-15 18:00 UTC, first offset = 3h → 21:00
        expected = datetime(2024, 1, 15, 21, 0, tzinfo=timezone.utc)
        assert result.hours[0].time == expected

    def test_times_are_utc(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing(SITE, LAT, LON)
        assert all(h.time.tzinfo == timezone.utc for h in result.hours)

    def test_site_key_preserved(self):
        with patch("seeing.requests.get", return_value=mock_response()):
            result = fetch_seeing("dark_site", LAT, LON)
        assert result.site_key == "dark_site"


# --- network errors ----------------------------------------------------------

class TestFetchSeeingErrors:
    def test_connection_error_returns_error_result(self):
        with patch("seeing.requests.get", side_effect=requests.ConnectionError("timeout")):
            result = fetch_seeing(SITE, LAT, LON)
        assert not result.ok
        assert result.error is not None
        assert result.hours == []

    def test_http_error_returns_error_result(self):
        resp = mock_response(raises=requests.HTTPError("503"))
        with patch("seeing.requests.get", return_value=resp):
            result = fetch_seeing(SITE, LAT, LON)
        assert not result.ok
        assert result.hours == []


# --- parse errors ------------------------------------------------------------

class TestFetchSeeingParseErrors:
    def test_missing_init_key_returns_error(self):
        with patch("seeing.requests.get", return_value=mock_response({"dataseries": []})):
            result = fetch_seeing(SITE, LAT, LON)
        assert not result.ok
        assert "Parse error" in result.error

    def test_missing_dataseries_key_returns_error(self):
        with patch("seeing.requests.get", return_value=mock_response({"init": "2024011518"})):
            result = fetch_seeing(SITE, LAT, LON)
        assert not result.ok
        assert "Parse error" in result.error

    def test_malformed_entry_returns_error(self):
        bad = {
            "init": "2024011518",
            "dataseries": [{"timepoint": 3, "seeing": "bad", "transparency": 5, "lifted_index": 1}],
        }
        with patch("seeing.requests.get", return_value=mock_response(bad)):
            result = fetch_seeing(SITE, LAT, LON)
        assert not result.ok
        assert "Parse error" in result.error

    def test_empty_dataseries_returns_empty_hours(self):
        data = {"init": "2024011518", "dataseries": []}
        with patch("seeing.requests.get", return_value=mock_response(data)):
            result = fetch_seeing(SITE, LAT, LON)
        assert result.ok
        assert result.hours == []
