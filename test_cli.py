"""Integration tests for the astro_alert.py CLI."""

import json
import sys
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import astro_alert
from astro_alert import build_parser, cmd_list_sites, cmd_add_site, cmd_run, _fetch_report
from moon import MoonInfo
from scorer import Score
from smtp_notifier import SiteReport


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

    def test_moon_rise_printed_when_present(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        rise = datetime(2024, 1, 15, 21, 0, tzinfo=timezone.utc)
        moon = MoonInfo(phase_pct=30, rise_utc=rise, set_utc=None,
                        transit_utc=None, is_up_at_midnight=True)
        score = Score(total=60, weather_score=25, seeing_score=20, moon_score=15,
                      go=True, summary="Good.", warnings=[])
        report = SiteReport(site_name="Home", drive_min=None, score=score, moon=moon)

        args = build_parser().parse_args(["--dry-run"])
        with patch("astro_alert._fetch_report", return_value=report):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "rises" in out
        assert "21:00Z" in out

    def test_moon_set_printed_when_present(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)

        moonset = datetime(2024, 1, 16, 2, 30, tzinfo=timezone.utc)
        moon = MoonInfo(phase_pct=80, rise_utc=None, set_utc=moonset,
                        transit_utc=None, is_up_at_midnight=False)
        score = Score(total=40, weather_score=20, seeing_score=15, moon_score=5,
                      go=False, summary="No-go.", warnings=[])
        report = SiteReport(site_name="Home", drive_min=None, score=score, moon=moon)

        args = build_parser().parse_args(["--dry-run"])
        with patch("astro_alert._fetch_report", return_value=report):
            cmd_run(args)

        out = capsys.readouterr().out
        assert "sets" in out
        assert "02:30Z" in out


# ---------------------------------------------------------------------------
# _fetch_report
# ---------------------------------------------------------------------------

class TestFetchReport:
    def _make_site(self):
        site = MagicMock()
        site.key = "test"
        site.lat = 35.99
        site.lon = -78.89
        site.name = "Test Site"
        site.drive_min = 30
        site.bortle = 5
        return site

    def test_returns_site_report(self):
        site = self._make_site()
        mock_weather = MagicMock()
        mock_seeing = MagicMock()
        mock_moon = MagicMock()
        mock_score = MagicMock()

        with patch("astro_alert.fetch_weather", return_value=mock_weather), \
             patch("astro_alert.fetch_seeing", return_value=mock_seeing), \
             patch("astro_alert.get_moon_info", return_value=mock_moon), \
             patch("astro_alert.score_night", return_value=mock_score):
            result = _fetch_report(site, date(2024, 1, 15))

        assert isinstance(result, SiteReport)
        assert result.site_name == "Test Site"
        assert result.drive_min == 30
        assert result.score is mock_score
        assert result.moon is mock_moon

    def test_passes_target_date_to_weather(self):
        site = self._make_site()
        target = date(2024, 6, 1)
        with patch("astro_alert.fetch_weather") as mock_fw, \
             patch("astro_alert.fetch_seeing", return_value=MagicMock()), \
             patch("astro_alert.get_moon_info", return_value=MagicMock()), \
             patch("astro_alert.score_night", return_value=MagicMock()):
            _fetch_report(site, target)
        mock_fw.assert_called_once_with("test", 35.99, -78.89, target_date=target)

    def test_passes_target_date_to_moon(self):
        site = self._make_site()
        target = date(2024, 6, 1)
        with patch("astro_alert.fetch_weather", return_value=MagicMock()), \
             patch("astro_alert.fetch_seeing", return_value=MagicMock()), \
             patch("astro_alert.get_moon_info") as mock_moon, \
             patch("astro_alert.score_night", return_value=MagicMock()):
            _fetch_report(site, target)
        mock_moon.assert_called_once_with(35.99, -78.89, target_date=target)

    def test_passes_bortle_to_scorer(self):
        site = self._make_site()
        site.bortle = 3
        mock_weather = MagicMock()
        mock_seeing = MagicMock()
        mock_moon = MagicMock()
        target = date(2024, 6, 1)
        with patch("astro_alert.fetch_weather", return_value=mock_weather), \
             patch("astro_alert.fetch_seeing", return_value=mock_seeing), \
             patch("astro_alert.get_moon_info", return_value=mock_moon), \
             patch("astro_alert.score_night") as mock_score:
            _fetch_report(site, target)
        mock_score.assert_called_once_with(mock_weather, mock_seeing, mock_moon,
                                           bortle=3, target_date=target)


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_dispatches_list_sites(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)
        monkeypatch.setattr(sys, "argv", ["astro_alert", "list-sites"])

        astro_alert.main()
        out = capsys.readouterr().out
        assert "Home" in out

    def test_main_dispatches_add_site(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)
        monkeypatch.setattr(sys, "argv", [
            "astro_alert", "add-site", "new", "New Spot",
            "36.0", "-79.0", "100", "3", "America/New_York"
        ])

        astro_alert.main()
        data = json.loads(p.read_text())
        assert "new" in data["sites"]

    def test_main_add_site_error_exits(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)
        monkeypatch.setattr(sys, "argv", [
            "astro_alert", "add-site", "home", "Duplicate",
            "36.0", "-79.0", "100", "3", "America/New_York"
        ])

        with patch("astro_alert.cmd_add_site", side_effect=KeyError("home already exists")):
            with pytest.raises(SystemExit) as exc:
                astro_alert.main()
        assert exc.value.code == 1

    def test_main_dispatches_run(self, tmp_path, monkeypatch, capsys):
        import site_manager as sm
        p = tmp_path / "sites.json"
        p.write_text(json.dumps(MINIMAL_SITES))
        monkeypatch.setattr(sm, "SITES_FILE", p)
        monkeypatch.setattr(sys, "argv", ["astro_alert", "--dry-run"])

        reports = [make_nogo_report("Home"), make_nogo_report("Dark Site", 70)]
        it = iter(reports)
        with patch("astro_alert._fetch_report", side_effect=lambda s, d: next(it)):
            astro_alert.main()

        out = capsys.readouterr().out
        assert "dry-run" in out
