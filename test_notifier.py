"""Tests for gmail_notifier.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from datetime import datetime, timezone
from moon import MoonInfo
from gmail_notifier import (SiteReport, send_multi_site_alert, send_test_email,
                             _format_report, _clean, _validate_address)
from scorer import Score

ENV = {
    "GMAIL_USER": "test@gmail.com",
    "GMAIL_APP_PASSWORD": "test-password",
    "ALERT_EMAIL_TO": "test@gmail.com",
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


def make_report(site_name="Backyard", drive_min=None, go=True, warnings=None):
    return SiteReport(
        site_name=site_name,
        drive_min=drive_min,
        score=make_score(go=go, warnings=warnings or []),
        moon=make_moon(),
    )


# --- _format_report ----------------------------------------------------------

class TestFormatReport:
    def test_go_label_present(self):
        lines = _format_report(make_report(go=True))
        assert any("GO" in l for l in lines)

    def test_nogo_label_present(self):
        lines = _format_report(make_report(go=False))
        assert any("NO-GO" in l for l in lines)

    def test_site_name_in_output(self):
        lines = _format_report(make_report(site_name="Dark Site"))
        assert any("Dark Site" in l for l in lines)

    def test_drive_time_shown(self):
        lines = _format_report(make_report(drive_min=48))
        assert any("48min" in l for l in lines)

    def test_home_shown_when_no_drive(self):
        lines = _format_report(make_report(drive_min=None))
        assert any("home" in l for l in lines)

    def test_warnings_included(self):
        lines = _format_report(make_report(warnings=["High wind", "Dew risk"]))
        combined = " ".join(lines)
        assert "High wind" in combined
        assert "Dew risk" in combined

    def test_no_warnings_line_when_empty(self):
        lines = _format_report(make_report(warnings=[]))
        assert len(lines) == 2  # name line + score line only


# --- send_multi_site_alert ---------------------------------------------------

class TestSendMultiSiteAlert:
    def _make_smtp(self):
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    def test_moon_rise_set_in_body(self):
        rise = datetime(2024, 1, 15, 20, 30, tzinfo=timezone.utc)
        set_ = datetime(2024, 1, 16, 7, 45, tzinfo=timezone.utc)
        moon_with_times = MoonInfo(
            phase_pct=30.0, rise_utc=rise, set_utc=set_,
            transit_utc=None, is_up_at_midnight=True,
        )
        report = SiteReport(
            site_name="Test", drive_min=60,
            score=make_score(), moon=moon_with_times,
        )
        sent_msg = {}
        mock_smtp = self._make_smtp()
        mock_smtp.send_message = lambda msg, **kw: sent_msg.update({"msg": msg})
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                send_multi_site_alert([report])
        body = sent_msg["msg"].get_content()
        assert "20:30" in body
        assert "07:45" in body

    def test_sends_successfully(self):
        mock_smtp = self._make_smtp()
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_multi_site_alert([make_report()])
        assert result.sent
        assert result.error is None

    def test_go_site_in_subject(self):
        sent_msg = {}
        mock_smtp = self._make_smtp()
        def capture(msg, **kw):
            sent_msg["msg"] = msg
        mock_smtp.send_message = capture

        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                send_multi_site_alert([make_report(site_name="Staunton River", go=True)])

        assert "GO" in sent_msg["msg"]["Subject"]
        assert "Staunton River" in sent_msg["msg"]["Subject"]

    def test_nogo_subject_shows_best_site(self):
        sent_msg = {}
        mock_smtp = self._make_smtp()
        mock_smtp.send_message = lambda msg, **kw: sent_msg.update({"msg": msg})

        reports = [
            make_report(site_name="Jordan Lake", go=False),
            make_report(site_name="Medoc Mountain", go=False),
        ]
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                send_multi_site_alert(reports)

        assert "NO-GO" in sent_msg["msg"]["Subject"]

    def test_night_label_in_subject(self):
        sent_msg = {}
        mock_smtp = self._make_smtp()
        mock_smtp.send_message = lambda msg, **kw: sent_msg.update({"msg": msg})

        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                send_multi_site_alert([make_report()], night_label="tomorrow night")

        assert "tomorrow night" in sent_msg["msg"]["Subject"]

    def test_missing_env_var_returns_error(self):
        incomplete = {k: v for k, v in ENV.items() if k != "GMAIL_APP_PASSWORD"}
        with patch.dict("os.environ", incomplete, clear=False):
            import os; os.environ.pop("GMAIL_APP_PASSWORD", None)
            result = send_multi_site_alert([make_report()])
        assert not result.sent
        assert "GMAIL_APP_PASSWORD" in result.error

    def test_auth_error_returns_error(self):
        import smtplib
        mock_smtp = self._make_smtp()
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_multi_site_alert([make_report()])

        assert not result.sent
        assert "auth" in result.error.lower()

    def test_never_raises(self):
        mock_smtp = self._make_smtp()
        mock_smtp.send_message.side_effect = RuntimeError("network down")

        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_multi_site_alert([make_report()])

        assert not result.sent
        assert result.error is not None


# --- _clean ------------------------------------------------------------------

class TestClean:
    def test_strips_regular_whitespace(self):
        assert _clean("  hello  ") == "hello"

    def test_strips_non_breaking_space(self):
        assert _clean("\xa0user@gmail.com\xa0") == "user@gmail.com"

    def test_returns_empty_for_none(self):
        assert _clean(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _clean("") == ""

    def test_nfkc_normalizes_fullwidth_chars(self):
        # Fullwidth digits/letters normalize to ASCII equivalents
        assert _clean("ａｂｃ") == "abc"


# --- _validate_address -------------------------------------------------------

class TestValidateAddress:
    def test_valid_address_returns_none(self):
        assert _validate_address("user@gmail.com") is None

    def test_empty_address_returns_error(self):
        assert _validate_address("") is not None

    def test_missing_at_returns_error(self):
        err = _validate_address("usergmail.com")
        assert err is not None
        assert "@" in err

    def test_empty_local_part_returns_error(self):
        err = _validate_address("@gmail.com")
        assert err is not None

    def test_double_dot_in_domain_returns_error(self):
        err = _validate_address("user@gmail..com")
        assert err is not None
        assert "invalid domain" in err

    def test_domain_missing_dot_returns_error(self):
        err = _validate_address("user@localhost")
        assert err is not None

    def test_domain_leading_dot_returns_error(self):
        err = _validate_address("user@.gmail.com")
        assert err is not None

    def test_domain_trailing_dot_returns_error(self):
        err = _validate_address("user@gmail.com.")
        assert err is not None

    def test_invalid_address_caught_by_send_multi_site_alert(self):
        env = {**ENV, "GMAIL_USER": "user@gmail..com"}
        with patch.dict("os.environ", env):
            result = send_multi_site_alert([make_report()])
        assert not result.sent
        assert "Invalid address" in result.error


# --- send_test_email ---------------------------------------------------------

class TestSendTestEmail:
    def _make_smtp(self):
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    def test_sends_successfully(self):
        mock_smtp = self._make_smtp()
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_test_email()
        assert result.sent
        assert result.error is None

    def test_returns_error_when_credentials_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            result = send_test_email()
        assert not result.sent
        assert "not configured" in result.error.lower()

    def test_returns_error_on_invalid_gmail_user(self):
        env = {**ENV, "GMAIL_USER": "notanemail"}
        with patch.dict("os.environ", env):
            result = send_test_email()
        assert not result.sent
        assert "Invalid address" in result.error

    def test_returns_error_on_double_dot_recipient(self):
        env = {**ENV, "ALERT_EMAIL_TO": "user@gmail..com"}
        with patch.dict("os.environ", env):
            result = send_test_email()
        assert not result.sent
        assert "Invalid address" in result.error

    def test_returns_error_on_auth_failure(self):
        import smtplib
        mock_smtp = self._make_smtp()
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad creds")
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_test_email()
        assert not result.sent
        assert "auth" in result.error.lower()

    def test_never_raises(self):
        mock_smtp = self._make_smtp()
        mock_smtp.send_message.side_effect = RuntimeError("timeout")
        with patch.dict("os.environ", ENV):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                result = send_test_email()
        assert not result.sent
        assert result.error is not None

    def test_uses_gmail_user_as_recipient_when_alert_to_not_set(self):
        env = {"GMAIL_USER": "me@gmail.com", "GMAIL_APP_PASSWORD": "pw"}
        calls = []
        mock_smtp = self._make_smtp()
        mock_smtp.send_message = lambda msg, **kw: calls.append(kw)
        with patch.dict("os.environ", env, clear=True):
            with patch("gmail_notifier.smtplib.SMTP", return_value=mock_smtp):
                send_test_email()
        assert calls[0]["to_addrs"] == ["me@gmail.com"]
