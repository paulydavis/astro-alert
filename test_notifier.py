"""Tests for notifier.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from moon import MoonInfo
from notifier import _build_message, send_alert
from scorer import Score

ENV = {
    "TWILIO_ACCOUNT_SID": "ACtest",
    "TWILIO_AUTH_TOKEN": "token",
    "TWILIO_FROM_NUMBER": "+10000000000",
    "TWILIO_TO_NUMBER": "+19999999999",
}


def make_score(go=True, total=72, weather=30, seeing=22, moon=20, warnings=None):
    return Score(
        total=total,
        weather_score=weather,
        seeing_score=seeing,
        moon_score=moon,
        go=go,
        summary="Good night — go image." if go else "No-go tonight.",
        warnings=warnings or [],
    )


def make_moon(phase=12.0):
    return MoonInfo(
        phase_pct=phase,
        rise_utc=None,
        set_utc=None,
        transit_utc=None,
        is_up_at_midnight=False,
    )


# --- message formatting ------------------------------------------------------

class TestBuildMessage:
    def test_go_label_present(self):
        msg = _build_message("Backyard", make_score(go=True), make_moon())
        assert "GO" in msg
        assert "NO-GO" not in msg

    def test_nogo_label_present(self):
        msg = _build_message("Backyard", make_score(go=False), make_moon())
        assert "NO-GO" in msg

    def test_site_name_in_message(self):
        msg = _build_message("Dark Site", make_score(), make_moon())
        assert "Dark Site" in msg

    def test_score_breakdown_present(self):
        msg = _build_message("Backyard", make_score(weather=30, seeing=22, moon=20), make_moon())
        assert "30/40" in msg
        assert "22/30" in msg
        assert "20/30" in msg

    def test_moon_phase_present(self):
        msg = _build_message("Backyard", make_score(), make_moon(phase=45.0))
        assert "45%" in msg

    def test_warnings_included(self):
        score = make_score(warnings=["High wind", "Dew risk"])
        msg = _build_message("Backyard", score, make_moon())
        assert "High wind" in msg
        assert "Dew risk" in msg

    def test_no_warnings_section_when_empty(self):
        msg = _build_message("Backyard", make_score(warnings=[]), make_moon())
        assert "Warnings" not in msg


# --- send_alert --------------------------------------------------------------

class TestSendAlert:
    def test_sends_successfully(self):
        mock_message = MagicMock()
        mock_message.sid = "SM123"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("os.environ", ENV):
            with patch("notifier.Client", return_value=mock_client):
                result = send_alert("Backyard", make_score(), make_moon())

        assert result.sent
        assert result.sid == "SM123"
        assert result.error is None

    def test_passes_correct_numbers(self):
        mock_message = MagicMock(sid="SM1")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("os.environ", ENV):
            with patch("notifier.Client", return_value=mock_client):
                send_alert("Backyard", make_score(), make_moon())

        _, kwargs = mock_client.messages.create.call_args
        assert kwargs["from_"] == ENV["TWILIO_FROM_NUMBER"]
        assert kwargs["to"] == ENV["TWILIO_TO_NUMBER"]

    def test_missing_env_var_returns_error(self):
        incomplete = {k: v for k, v in ENV.items() if k != "TWILIO_AUTH_TOKEN"}
        with patch.dict("os.environ", incomplete, clear=False):
            # Unset the key entirely
            import os
            os.environ.pop("TWILIO_AUTH_TOKEN", None)
            result = send_alert("Backyard", make_score(), make_moon())

        assert not result.sent
        assert "TWILIO_AUTH_TOKEN" in result.error

    def test_twilio_exception_returns_error(self):
        from twilio.base.exceptions import TwilioRestException
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = TwilioRestException(
            status=401, uri="/Messages", msg="Unauthorized"
        )

        with patch.dict("os.environ", ENV):
            with patch("notifier.Client", return_value=mock_client):
                result = send_alert("Backyard", make_score(), make_moon())

        assert not result.sent
        assert result.error is not None

    def test_never_raises(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("network down")

        with patch.dict("os.environ", ENV):
            with patch("notifier.Client", return_value=mock_client):
                result = send_alert("Backyard", make_score(), make_moon())

        assert not result.sent
        assert "Unexpected error" in result.error
