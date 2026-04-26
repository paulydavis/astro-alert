"""Integration tests for the astro_alert.py CLI."""

import json
import sys
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import astro_alert
from astro_alert import build_parser, cmd_list_sites, cmd_add_site, cmd_run
from moon import MoonInfo
from scorer import Score
from gmail_notifier import SiteReport


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_SITES = {
    "active_site": "home",
    "sites": {
        "home": {
            "name": "Home",
            "lat": 35.99, "lon": -78.89, "elevation_m": 120,
            "bortle": 7, "timezone": "America/New_York",
            "drive_min": None, "notes": "backyard",
        },
        "dark": {
            "name": "Dark Site",
            "lat": 36.26, "lon": -77.88, "elevation_m": 99,
            "bortle": 4, "timezone": "America/New_York",
            "drive_min": 70, "notes": "best nearby",
        },
    },
}


def make_nogo_report(site_name="Home", drive_min=None):
    score = Score(total=20, weather_score=5, seeing_score=10, moon_score=5,
                  go=False, summary="No-go tonight.", warnings=["Overcast"])
    moon = MoonInfo(phase_pct=50, rise_utc=None, set_utc=None,
                    transit_utc=None, is_up_at_midnight=True)
    return SiteReport(site_name=site_name, drive_min=drive_min, score=score, moon=moon)


def make_go_report(site_name="Dark Site", drive_min=70):
    score = Score(total=75, weather_score=35, seeing_score=25, moon_score=15,
                  go=True, summary="Good night — go image.", warnings=[])
    moon = MoonInfo(phase_pct=10, rise_utc=None, set_utc=None,
                    transit_utc=None, is_up_at_midnight=False)
    return SiteReport(site_name=site_name, drive_min=drive_min, score=score, moon=moon)


# ---------------------------------------------------------------------------
# list-sites
# ---------------------------------------------------------------------------

class TestListSites:
    def test_lists_all_sites(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args(["list-sites"])
        cmd_list_sites(args)
        out = capsys.readouterr().out
        assert "Home" in out
        assert "Dark Site" in out

    def test_active_site_marked(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args(["list-sites"])
        cmd_list_sites(args)
        out = capsys.readouterr().out
        lines = out.splitlines()
        active = [l for l in lines if l.startswith("*")]
        assert len(active) == 1
        assert "Home" in active[0]

    def test_empty_sites(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps({"active_site": None, "sites": {}}))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args(["list-sites"])
        cmd_list_sites(args)
        out = capsys.readouterr().out
        assert "No sites" in out


# ---------------------------------------------------------------------------
# add-site
# ---------------------------------------------------------------------------

class TestAddSite:
    def test_adds_site(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args([
            "add-site", "new", "New Spot", "36.0", "-79.0", "100", "3", "America/New_York"
        ])
        cmd_add_site(args)
        data = json.loads(p.read_text())
        assert "new" in data["sites"]

    def test_add_site_with_set_active(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args([
            "add-site", "new", "New Spot", "36.0", "-79.0", "100", "3",
            "America/New_York", "--set-active"
        ])
        cmd_add_site(args)
        data = json.loads(p.read_text())
        assert data["active_site"] == "new"
        out = capsys.readouterr().out
        assert "Added and activated" in out


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------

class TestCmdRun:
    def _patch_fetch(self, reports):
        """Patch _fetch_report to return reports in order."""
        it = iter(reports)
        return patch("astro_alert._fetch_report", side_effect=lambda site, d: next(it))

    def test_dry_run_does_not_send_email(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        reports = [make_nogo_report("Home"), make_nogo_report("Dark Site", 70)]
        args = build_parser().parse_args(["--dry-run"])
        with self._patch_fetch(reports):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "email not sent" in out

    def test_only_if_go_suppresses_when_all_nogo(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        reports = [make_nogo_report("Home"), make_nogo_report("Dark Site", 70)]
        args = build_parser().parse_args(["--only-if-go", "--dry-run"])
        with self._patch_fetch(reports):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "skipping email" in out

    def test_only_if_go_sends_when_site_is_go(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        reports = [make_nogo_report("Home"), make_go_report("Dark Site", 70)]
        args = build_parser().parse_args(["--only-if-go", "--dry-run"])
        with self._patch_fetch(reports):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "skipping email" not in out
        assert "dry-run" in out

    def test_tomorrow_flag_uses_next_date(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        captured_dates = []
        def capture_fetch(site, target_date):
            captured_dates.append(target_date)
            return make_nogo_report(site.name, site.drive_min)

        today = datetime.now(timezone.utc).date()
        args = build_parser().parse_args(["--tomorrow", "--dry-run"])
        with patch("astro_alert._fetch_report", side_effect=capture_fetch):
            cmd_run(args)

        from datetime import timedelta
        assert all(d == today + timedelta(days=1) for d in captured_dates)

    def test_single_site_via_flag(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args(["--site", "dark", "--dry-run"])
        with patch("astro_alert._fetch_report", return_value=make_go_report()):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "1 site(s)" in out

    def test_invalid_site_exits_with_error(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        args = build_parser().parse_args(["--site", "nonexistent", "--dry-run"])
        with pytest.raises(SystemExit) as exc:
            cmd_run(args)
        assert exc.value.code == 1

    def test_email_sent_on_success(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        reports = [make_go_report("Dark Site", 70), make_nogo_report("Home")]
        mock_result = MagicMock()
        mock_result.sent = True

        args = build_parser().parse_args([])
        with self._patch_fetch(reports):
            with patch("astro_alert.send_multi_site_alert", return_value=mock_result):
                cmd_run(args)

        out = capsys.readouterr().out
        assert "Alert sent" in out

    def test_email_failure_exits_with_error(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        reports = [make_nogo_report("Home"), make_nogo_report("Dark Site", 70)]
        mock_result = MagicMock()
        mock_result.sent = False
        mock_result.error = "SMTP timeout"

        args = build_parser().parse_args([])
        with self._patch_fetch(reports):
            with patch("astro_alert.send_multi_site_alert", return_value=mock_result):
                with pytest.raises(SystemExit) as exc:
                    cmd_run(args)
        assert exc.value.code == 1
