"""Tests for gui.py — AstroAlertApp and SiteDialog."""

import json
import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

# Skip entire module when no display is available (headless CI).
_TK_AVAILABLE = True
try:
    _r = tk.Tk()
    _r.withdraw()
    _r.destroy()
except Exception:
    _TK_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _TK_AVAILABLE, reason="No display available")

import site_manager as sm
import gui
from gui import AstroAlertApp, SiteDialog


# ── Shared data ───────────────────────────────────────────────────────────────

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
            "drive_min": 70, "notes": None,
        },
    },
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sites_file(tmp_path, monkeypatch):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps(MINIMAL_SITES))
    monkeypatch.setattr(sm, "SITES_FILE", path)
    return path


@pytest.fixture()
def app(sites_file):
    with patch("scheduler_setup.get_schedule_status", return_value=(False, "")):
        a = AstroAlertApp()
        a.withdraw()
    yield a
    if a.winfo_exists():
        a.destroy()


@pytest.fixture()
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    if r.winfo_exists():
        r.destroy()


@pytest.fixture()
def fake_env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    import data_dir
    monkeypatch.setattr(data_dir, "ENV_FILE", path)
    return path


# ── AstroAlertApp: initialisation ─────────────────────────────────────────────

class TestAppInit:
    def test_window_title(self, app):
        assert app.title() == "Astro Alert"

    def test_has_notebook_with_four_tabs(self, app):
        assert hasattr(app, "_nb")
        assert app._nb.index("end") == 4

    def test_run_button_exists(self, app):
        assert hasattr(app, "_run_btn")

    def test_site_combo_exists(self, app):
        assert hasattr(app, "_site_combo")

    def test_output_widget_exists(self, app):
        assert hasattr(app, "_output")

    def test_treeview_exists(self, app):
        assert hasattr(app, "_tree")

    def test_status_bar_initial_text(self, app):
        assert app._status_var.get() == "Ready."

    def test_dry_run_defaults_to_true(self, app):
        assert app._dry_run_var.get() is True

    def test_night_defaults_to_tonight(self, app):
        assert app._night_var.get() == "tonight"

    def test_schedule_labels_exist(self, app):
        assert hasattr(app, "_sched_title")
        assert hasattr(app, "_sched_detail")


# ── AstroAlertApp: _refresh_sites ─────────────────────────────────────────────

class TestRefreshSites:
    def test_populates_treeview_with_all_sites(self, app):
        app._refresh_sites()
        keys = set(app._tree.get_children())
        assert "home" in keys
        assert "dark" in keys

    def test_active_site_marked_with_star(self, app):
        app._refresh_sites()
        vals = app._tree.item("home", "values")
        assert vals[-1] == "★"

    def test_inactive_site_has_no_star(self, app):
        app._refresh_sites()
        vals = app._tree.item("dark", "values")
        assert vals[-1] == ""

    def test_drive_time_shown_for_site_with_drive(self, app):
        app._refresh_sites()
        vals = app._tree.item("dark", "values")
        assert "70 min" in vals

    def test_drive_dash_for_home_site(self, app):
        app._refresh_sites()
        vals = app._tree.item("home", "values")
        assert "—" in vals

    def test_combobox_contains_all_sites_option(self, app):
        app._refresh_sites()
        assert "All sites" in app._site_combo["values"]

    def test_combobox_contains_site_names(self, app):
        app._refresh_sites()
        options = list(app._site_combo["values"])
        assert any("home" in o for o in options)
        assert any("dark" in o for o in options)

    def test_combobox_first_option_is_all_sites(self, app):
        app._refresh_sites()
        assert app._site_combo["values"][0] == "All sites"

    def test_handles_missing_sites_file_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sm, "SITES_FILE", tmp_path / "nonexistent.json")
        with patch("scheduler_setup.get_schedule_status", return_value=(False, "")):
            a = AstroAlertApp()
            a.withdraw()
        a._refresh_sites()  # should not raise
        a.destroy()

    def test_site_var_reset_to_all_sites_when_stale(self, app):
        app._site_var.set("old: Stale Site")  # value not in current sites
        app._refresh_sites()
        assert app._site_var.get() == "All sites"


# ── AstroAlertApp: _display_output ────────────────────────────────────────────

class TestDisplayOutput:
    def _line_tags(self, app, line=1):
        return app._output.tag_names(f"{line}.0")

    def test_go_line_gets_go_tag(self, app):
        app._display_output("  GO    75/100  dark    Dark Site\n")
        assert "go" in self._line_tags(app)

    def test_nogo_line_gets_nogo_tag(self, app):
        app._display_output("  NO-GO 20/100  home  Home\n")
        assert "nogo" in self._line_tags(app)

    def test_moon_line_gets_moon_tag(self, app):
        app._display_output("Moon: 70% illuminated  rises 19:20Z\n")
        assert "moon" in self._line_tags(app)

    def test_rises_line_gets_moon_tag(self, app):
        app._display_output("  rises 19:20Z\n")
        assert "moon" in self._line_tags(app)

    def test_dry_run_line_gets_warn_tag(self, app):
        app._display_output("(dry-run: email not sent)\n")
        assert "warn" in self._line_tags(app)

    def test_skipping_email_gets_warn_tag(self, app):
        app._display_output("No sites are GO — skipping email (--only-if-go).\n")
        assert "warn" in self._line_tags(app)

    def test_alert_sent_line_gets_ok_tag(self, app):
        app._display_output("Alert sent via EMAIL\n")
        assert "ok" in self._line_tags(app)

    def test_fetching_line_gets_dim_tag(self, app):
        app._display_output("Fetching conditions…\n")
        assert "dim" in self._line_tags(app)

    def test_plain_line_gets_no_special_tag(self, app):
        app._display_output("Some ordinary text\n")
        tags = self._line_tags(app)
        for t in ("go", "nogo", "moon", "warn", "ok", "dim", "err"):
            assert t not in tags

    def test_errors_appended_to_output(self, app):
        app._display_output("main output\n", errors="network failure")
        content = app._output.get("1.0", "end")
        assert "network failure" in content

    def test_previous_output_cleared_on_new_call(self, app):
        app._display_output("first run\n")
        app._display_output("second run\n")
        content = app._output.get("1.0", "end")
        assert "first run" not in content
        assert "second run" in content

    def test_status_set_to_forecast_complete(self, app):
        app._display_output("GO 75/100\n")
        assert app._status_var.get() == "Forecast complete."


# ── AstroAlertApp: _run_forecast arg building ─────────────────────────────────

class TestRunForecast:
    def _captured_args(self, app):
        """Call _run_forecast with cmd_run mocked; return the args Namespace."""
        captured = []
        with patch("gui.cmd_run", side_effect=lambda a: captured.append(a)):
            app._run_forecast()
            app.update()
        return captured[0] if captured else None

    def test_tonight_does_not_set_tomorrow(self, app):
        app._night_var.set("tonight")
        app._dry_run_var.set(True)
        args = self._captured_args(app)
        assert args is not None
        assert args.tomorrow is False

    def test_tomorrow_night_sets_tomorrow_flag(self, app):
        app._night_var.set("tomorrow")
        app._dry_run_var.set(True)
        args = self._captured_args(app)
        assert args.tomorrow is True

    def test_dry_run_checked_sets_flag(self, app):
        app._night_var.set("tonight")
        app._dry_run_var.set(True)
        args = self._captured_args(app)
        assert args.dry_run is True

    def test_dry_run_unchecked_omits_flag(self, app):
        app._night_var.set("tonight")
        app._dry_run_var.set(False)
        args = self._captured_args(app)
        assert args.dry_run is False

    def test_all_sites_sets_no_site_arg(self, app):
        app._site_var.set("All sites")
        app._dry_run_var.set(True)
        args = self._captured_args(app)
        assert args.site is None

    def test_specific_site_sets_site_key(self, app):
        app._site_var.set("home: Home")
        app._dry_run_var.set(True)
        args = self._captured_args(app)
        assert args.site == "home"

    def test_button_re_enabled_after_run(self, app):
        app._dry_run_var.set(True)
        with patch("gui.cmd_run"):
            app._run_forecast()
            app.update()
        assert str(app._run_btn.cget("state")) != "disabled"


# ── AstroAlertApp: _start_forecast ────────────────────────────────────────────

class TestStartForecast:
    def test_disables_button_while_running(self, app):
        with patch("threading.Thread") as mock_thread:
            app._start_forecast()
        assert str(app._run_btn.cget("state")) == "disabled"

    def test_button_text_changes_to_running(self, app):
        with patch("threading.Thread") as mock_thread:
            app._start_forecast()
        assert "Running" in str(app._run_btn.cget("text"))


# ── AstroAlertApp: schedule tab ───────────────────────────────────────────────

class TestScheduleStatus:
    def test_shows_installed_when_cron_present(self, app):
        with patch("scheduler_setup.get_schedule_status", return_value=(True, "0 18 * * *")):
            app._refresh_schedule_status()
        assert "installed" in app._sched_title.cget("text").lower()

    def test_shows_not_scheduled_when_absent(self, app):
        with patch("scheduler_setup.get_schedule_status", return_value=(False, "")):
            app._refresh_schedule_status()
        assert "not scheduled" in app._sched_title.cget("text").lower()

    def test_shows_warning_on_exception(self, app):
        with patch("scheduler_setup.get_schedule_status", side_effect=RuntimeError("oops")):
            app._refresh_schedule_status()
        assert "could not" in app._sched_title.cget("text").lower()


class TestScheduleInstall:
    def test_install_calls_installer(self, app):
        with patch("scheduler_setup.install_schedule") as mock_install, \
             patch("scheduler_setup.get_schedule_status", return_value=(True, "")), \
             patch("tkinter.messagebox.showinfo"):
            app._install_schedule()
        mock_install.assert_called_once()

    def test_install_refreshes_status_afterwards(self, app):
        with patch("scheduler_setup.install_schedule"), \
             patch("scheduler_setup.get_schedule_status", return_value=(True, "")) as mock_status, \
             patch("tkinter.messagebox.showinfo"):
            app._install_schedule()
        mock_status.assert_called()

    def test_install_error_shows_error_dialog(self, app):
        with patch("scheduler_setup.install_schedule", side_effect=RuntimeError("fail")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._install_schedule()
        mock_err.assert_called_once()

    def test_remove_confirmed_calls_uninstaller(self, app):
        with patch("scheduler_setup.uninstall_schedule") as mock_un, \
             patch("scheduler_setup.get_schedule_status", return_value=(False, "")), \
             patch("tkinter.messagebox.askyesno", return_value=True):
            app._remove_schedule()
        mock_un.assert_called_once()

    def test_remove_cancelled_skips_uninstall(self, app):
        with patch("scheduler_setup.uninstall_schedule") as mock_un, \
             patch("tkinter.messagebox.askyesno", return_value=False):
            app._remove_schedule()
        mock_un.assert_not_called()


# ── AstroAlertApp: site actions ───────────────────────────────────────────────

class TestSiteActions:
    def test_set_active_with_no_selection_shows_info(self, app):
        with patch("tkinter.messagebox.showinfo") as mock_info:
            app._set_active_site()
        mock_info.assert_called_once()

    def test_set_active_calls_set_active_site_with_key(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("gui.set_active_site") as mock_set:
            app._set_active_site()
        mock_set.assert_called_once_with("dark")

    def test_set_active_updates_status_bar(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("gui.set_active_site"):
            app._set_active_site()
        assert "dark" in app._status_var.get()

    def test_delete_with_no_selection_shows_info(self, app):
        with patch("tkinter.messagebox.showinfo") as mock_info:
            app._delete_site()
        mock_info.assert_called_once()

    def test_delete_confirmed_calls_delete_site(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("gui.delete_site") as mock_del:
            app._delete_site()
        mock_del.assert_called_once_with("dark")

    def test_delete_cancelled_skips_delete(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("tkinter.messagebox.askyesno", return_value=False), \
             patch("gui.delete_site") as mock_del:
            app._delete_site()
        mock_del.assert_not_called()


# ── AstroAlertApp: add / edit dialog integration ─────────────────────────────

class TestAddEditDialogIntegration:
    def _mock_dialog(self, result):
        dlg = MagicMock()
        dlg.result = result
        return dlg

    def test_add_site_calls_add_site_with_result(self, app):
        result = {"key": "new", "name": "New", "lat": 36.0, "lon": -79.0,
                  "elevation_m": 100.0, "bortle": 4, "timezone": "America/New_York",
                  "drive_min": None, "notes": None, "set_active": False}
        with patch("gui.SiteDialog", return_value=self._mock_dialog(result)), \
             patch.object(app, "wait_window"), \
             patch("gui.add_site") as mock_add:
            app._add_site_dialog()
        mock_add.assert_called_once_with(**result)

    def test_add_site_no_call_when_dialog_cancelled(self, app):
        with patch("gui.SiteDialog", return_value=self._mock_dialog(None)), \
             patch.object(app, "wait_window"), \
             patch("gui.add_site") as mock_add:
            app._add_site_dialog()
        mock_add.assert_not_called()

    def test_edit_site_no_selection_shows_info(self, app):
        with patch("tkinter.messagebox.showinfo") as mock_info:
            app._edit_site_dialog()
        mock_info.assert_called_once()

    def test_edit_site_with_selection_calls_add_site(self, app):
        app._refresh_sites()
        app._tree.selection_set("home")
        result = {"key": "home", "name": "Home Updated", "lat": 35.99, "lon": -78.89,
                  "elevation_m": 120.0, "bortle": 7, "timezone": "America/New_York",
                  "drive_min": None, "notes": None, "set_active": False}
        with patch("gui.SiteDialog", return_value=self._mock_dialog(result)), \
             patch.object(app, "wait_window"), \
             patch("gui.add_site") as mock_add:
            app._edit_site_dialog()
        mock_add.assert_called_once_with(**result)


# ── SiteDialog: initialisation ────────────────────────────────────────────────

class TestSiteDialogInit:
    def test_add_mode_has_empty_fields(self, root):
        dlg = SiteDialog(root, title="Add Site")
        assert dlg._vars["key"].get() == ""
        assert dlg._vars["name"].get() == ""
        assert dlg._vars["lat"].get() == ""
        dlg.destroy()

    def test_edit_mode_pre_fills_fields(self, root, sites_file):
        site = sm.get_active_site()
        dlg = SiteDialog(root, title="Edit Site", site=site, key="home")
        assert dlg._vars["name"].get() == "Home"
        assert dlg._vars["lat"].get() == "35.99"
        assert dlg._vars["lon"].get() == "-78.89"
        assert dlg._vars["bortle"].get() == "7"
        assert dlg._vars["timezone"].get() == "America/New_York"
        dlg.destroy()

    def test_edit_mode_sets_key_var(self, root, sites_file):
        site = sm.get_active_site()
        dlg = SiteDialog(root, title="Edit Site", site=site, key="home")
        assert dlg._vars["key"].get() == "home"
        dlg.destroy()

    def test_editing_key_stored(self, root, sites_file):
        site = sm.get_active_site()
        dlg = SiteDialog(root, title="Edit Site", site=site, key="home")
        assert dlg._editing_key == "home"
        dlg.destroy()

    def test_result_initially_none(self, root):
        dlg = SiteDialog(root, title="Add Site")
        assert dlg.result is None
        dlg.destroy()


# ── SiteDialog: _save validation ─────────────────────────────────────────────

class TestSiteDialogSave:
    def _filled_dialog(self, root, **overrides):
        dlg = SiteDialog(root, title="Add Site")
        defaults = {
            "key": "test", "name": "Test Site", "lat": "36.0",
            "lon": "-79.0", "elevation_m": "100", "bortle": "5",
            "timezone": "America/New_York",
        }
        defaults.update(overrides)
        for field, val in defaults.items():
            dlg._vars[field].set(val)
        return dlg

    def test_save_returns_correct_result(self, root):
        dlg = self._filled_dialog(root)
        dlg._save()
        assert dlg.result is not None
        assert dlg.result["key"] == "test"
        assert dlg.result["name"] == "Test Site"
        assert dlg.result["lat"] == 36.0
        assert dlg.result["bortle"] == 5
        assert dlg.result["timezone"] == "America/New_York"

    def test_save_fails_on_missing_required_name(self, root):
        dlg = self._filled_dialog(root, name="")
        with patch("tkinter.messagebox.showerror"):
            dlg._save()
        assert dlg.result is None
        dlg.destroy()

    def test_save_fails_on_missing_lat(self, root):
        dlg = self._filled_dialog(root, lat="")
        with patch("tkinter.messagebox.showerror"):
            dlg._save()
        assert dlg.result is None
        dlg.destroy()

    def test_save_fails_on_bortle_above_9(self, root):
        dlg = self._filled_dialog(root, bortle="10")
        with patch("tkinter.messagebox.showerror") as mock_err:
            dlg._save()
        assert dlg.result is None
        mock_err.assert_called_once()
        dlg.destroy()

    def test_save_fails_on_bortle_zero(self, root):
        dlg = self._filled_dialog(root, bortle="0")
        with patch("tkinter.messagebox.showerror"):
            dlg._save()
        assert dlg.result is None
        dlg.destroy()

    def test_save_fails_on_non_numeric_lat(self, root):
        dlg = self._filled_dialog(root, lat="not-a-number")
        with patch("tkinter.messagebox.showerror"):
            dlg._save()
        assert dlg.result is None
        dlg.destroy()

    def test_optional_fields_can_be_empty(self, root):
        dlg = self._filled_dialog(root)
        dlg._vars["drive_min"].set("")
        dlg._vars["notes"].set("")
        dlg._save()
        assert dlg.result is not None
        assert dlg.result["drive_min"] is None
        assert dlg.result["notes"] is None

    def test_set_active_included_in_result(self, root):
        dlg = self._filled_dialog(root)
        dlg._set_active_var.set(True)
        dlg._save()
        assert dlg.result["set_active"] is True

    def test_editing_key_used_in_result(self, root, sites_file):
        site = sm.get_active_site()
        dlg = SiteDialog(root, title="Edit Site", site=site, key="home")
        dlg._save()
        assert dlg.result["key"] == "home"


# ── SiteDialog: geocoding ─────────────────────────────────────────────────────

class TestSiteDialogGeocode:
    GEO_RESULT = [{"lat": "36.10000", "lon": "-79.20000",
                   "display_name": "Chapel Hill, Orange County, NC, USA"}]

    def _setup_geo(self, dlg):
        dlg._geo_results = self.GEO_RESULT
        dlg._results_combo.configure(
            values=[r["display_name"] for r in self.GEO_RESULT],
            state="readonly",
        )
        dlg._results_combo.current(0)

    def test_on_result_selected_fills_lat_lon(self, root):
        dlg = SiteDialog(root, title="Add Site")
        self._setup_geo(dlg)
        with patch.object(dlg, "_fetch_elevation"):
            dlg._on_result_selected()
        assert dlg._vars["lat"].get() == "36.10000"
        assert dlg._vars["lon"].get() == "-79.20000"
        dlg.destroy()

    def test_on_result_selected_fills_name(self, root):
        dlg = SiteDialog(root, title="Add Site")
        self._setup_geo(dlg)
        with patch.object(dlg, "_fetch_elevation"):
            dlg._on_result_selected()
        assert dlg._vars["name"].get() == "Chapel Hill"
        dlg.destroy()

    def test_on_result_selected_auto_generates_key(self, root):
        dlg = SiteDialog(root, title="Add Site")
        self._setup_geo(dlg)
        with patch.object(dlg, "_fetch_elevation"):
            dlg._on_result_selected()
        assert dlg._vars["key"].get() == "chapel_hill"
        dlg.destroy()

    def test_on_result_selected_does_not_overwrite_key_on_edit(self, root, sites_file):
        site = sm.get_active_site()
        dlg = SiteDialog(root, title="Edit Site", site=site, key="home")
        self._setup_geo(dlg)
        with patch.object(dlg, "_fetch_elevation"):
            dlg._on_result_selected()
        assert dlg._vars["key"].get() == "home"
        dlg.destroy()

    def test_fetch_elevation_fills_elevation_field(self, root):
        dlg = SiteDialog(root, title="Add Site")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"elevation": [153.7]}
        with patch("requests.get", return_value=mock_resp):
            dlg._fetch_elevation(36.0, -79.0)
            dlg.update()
        assert dlg._vars["elevation_m"].get() == "154"
        dlg.destroy()

    def test_fetch_elevation_ignores_network_errors(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._vars["elevation_m"].set("200")
        with patch("requests.get", side_effect=OSError("timeout")):
            dlg._fetch_elevation(36.0, -79.0)
        assert dlg._vars["elevation_m"].get() == "200"
        dlg.destroy()

    def test_geocode_done_populates_combo(self, root):
        dlg = SiteDialog(root, title="Add Site")
        with patch.object(dlg, "_on_result_selected"):
            dlg._geocode_done(self.GEO_RESULT)
        assert len(dlg._geo_results) == 1
        assert len(dlg._results_combo["values"]) == 1
        dlg.destroy()

    def test_geocode_done_no_results_shows_info(self, root):
        dlg = SiteDialog(root, title="Add Site")
        with patch("tkinter.messagebox.showinfo") as mock_info:
            dlg._geocode_done([])
        mock_info.assert_called_once()
        dlg.destroy()

    def test_geocode_error_shows_error_dialog(self, root):
        dlg = SiteDialog(root, title="Add Site")
        with patch("tkinter.messagebox.showerror") as mock_err:
            dlg._geocode_error("connection refused")
        mock_err.assert_called_once()
        dlg.destroy()

    def test_do_geocode_calls_nominatim(self, root):
        dlg = SiteDialog(root, title="Add Site")
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.GEO_RESULT
        with patch("requests.get", return_value=mock_resp) as mock_get, \
             patch("threading.Thread"):  # suppress elevation fetch thread
            dlg._do_geocode("Chapel Hill NC")
            dlg.update()
        all_urls = [c[0][0] for c in mock_get.call_args_list]
        assert any("nominatim" in url for url in all_urls)
        dlg.destroy()

    def test_do_geocode_network_error_calls_geocode_error(self, root):
        dlg = SiteDialog(root, title="Add Site")
        with patch("requests.get", side_effect=OSError("timeout")):
            dlg._do_geocode("nowhere")
            dlg.update()  # process after(0, _geocode_error, ...)
        # _geocode_error re-enables the button
        assert str(dlg._search_btn.cget("state")) != "disabled"
        dlg.destroy()

    def test_on_result_selected_early_return_when_no_results(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._geo_results = []
        dlg._on_result_selected()  # idx=-1 with empty results — should not raise
        dlg.destroy()

    def test_search_location_empty_query_does_nothing(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._search_var.set("")
        with patch("threading.Thread") as mock_thread:
            dlg._search_location()
        mock_thread.assert_not_called()
        dlg.destroy()

    def test_search_location_valid_query_starts_thread(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._search_var.set("Durham NC")
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            dlg._search_location()
        mock_thread.assert_called_once()
        dlg.destroy()

    def test_search_location_disables_button(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._search_var.set("Durham NC")
        with patch("threading.Thread"):
            dlg._search_location()
        assert str(dlg._search_btn.cget("state")) == "disabled"
        dlg.destroy()

    def test_open_bortle_map_with_coords(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._vars["lat"].set("36.0")
        dlg._vars["lon"].set("-79.0")
        with patch("webbrowser.open") as mock_open:
            dlg._open_bortle_map()
        url = mock_open.call_args[0][0]
        assert "lightpollutionmap" in url
        assert "36.0" in url
        dlg.destroy()

    def test_open_bortle_map_without_coords_uses_fallback(self, root):
        dlg = SiteDialog(root, title="Add Site")
        dlg._vars["lat"].set("")
        dlg._vars["lon"].set("")
        with patch("webbrowser.open") as mock_open:
            dlg._open_bortle_map()
        url = mock_open.call_args[0][0]
        assert url == "https://www.lightpollutionmap.info/"
        dlg.destroy()


# ── Edge cases: exception handlers and SystemExit ─────────────────────────────

class TestExceptionHandlers:
    def test_run_forecast_catches_system_exit(self, app):
        app._dry_run_var.set(True)
        with patch("gui.cmd_run", side_effect=SystemExit(1)):
            app._run_forecast()  # should not propagate SystemExit
            app.update()

    def test_add_site_error_shows_dialog(self, app):
        result = {"key": "x", "name": "X", "lat": 36.0, "lon": -79.0,
                  "elevation_m": 100.0, "bortle": 4, "timezone": "America/New_York",
                  "drive_min": None, "notes": None, "set_active": False}
        mock_dlg = MagicMock()
        mock_dlg.result = result
        with patch("gui.SiteDialog", return_value=mock_dlg), \
             patch.object(app, "wait_window"), \
             patch("gui.add_site", side_effect=ValueError("duplicate key")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._add_site_dialog()
        mock_err.assert_called_once()

    def test_edit_site_error_shows_dialog(self, app):
        app._refresh_sites()
        app._tree.selection_set("home")
        result = {"key": "home", "name": "Home", "lat": 35.99, "lon": -78.89,
                  "elevation_m": 120.0, "bortle": 7, "timezone": "America/New_York",
                  "drive_min": None, "notes": None, "set_active": False}
        mock_dlg = MagicMock()
        mock_dlg.result = result
        with patch("gui.SiteDialog", return_value=mock_dlg), \
             patch.object(app, "wait_window"), \
             patch("gui.add_site", side_effect=ValueError("bad data")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._edit_site_dialog()
        mock_err.assert_called_once()

    def test_set_active_error_shows_dialog(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("gui.set_active_site", side_effect=KeyError("dark")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._set_active_site()
        mock_err.assert_called_once()

    def test_delete_site_error_shows_dialog(self, app):
        app._refresh_sites()
        app._tree.selection_set("dark")
        with patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("gui.delete_site", side_effect=KeyError("dark")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._delete_site()
        mock_err.assert_called_once()

    def test_remove_schedule_error_shows_dialog(self, app):
        with patch("tkinter.messagebox.askyesno", return_value=True), \
             patch("scheduler_setup.uninstall_schedule", side_effect=RuntimeError("fail")), \
             patch("tkinter.messagebox.showerror") as mock_err:
            app._remove_schedule()
        mock_err.assert_called_once()


# ── Settings tab ──────────────────────────────────────────────────────────────

class TestSettingsTab:
    def test_settings_tab_exists(self, app):
        assert hasattr(app, "_tab_settings")

    def test_credential_vars_exist(self, app):
        assert hasattr(app, "_cred_user_var")
        assert hasattr(app, "_cred_pass_var")
        assert hasattr(app, "_cred_to_var")

    def test_test_button_exists(self, app):
        assert hasattr(app, "_test_btn")

    def test_load_credentials_sets_vars_from_env_file(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        fake_env.write_text("SMTP_USER=test@example.com\nSMTP_PASSWORD=secret\n")
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._load_credentials_to_form()
        assert app._cred_user_var.get() == "test@example.com"
        assert app._cred_pass_var.get() == "secret"

    def test_load_credentials_empty_when_no_env_file(self, app, tmp_path, monkeypatch):
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", tmp_path / "nonexistent.env")
        app._load_credentials_to_form()
        assert app._cred_user_var.get() == ""
        assert app._cred_pass_var.get() == ""

    def test_save_credentials_writes_env_file(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._cred_user_var.set("me@gmail.com")
        app._cred_pass_var.set("mypassword")
        with patch("tkinter.messagebox.showinfo"):
            app._save_credentials()
        from dotenv import dotenv_values
        vals = dotenv_values(fake_env)
        assert vals["SMTP_USER"] == "me@gmail.com"
        assert vals["SMTP_PASSWORD"] == "mypassword"

    def test_save_credentials_omits_empty_fields(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._cred_user_var.set("me@gmail.com")
        app._cred_pass_var.set("")
        app._cred_to_var.set("")
        with patch("tkinter.messagebox.showinfo"):
            app._save_credentials()
        content = fake_env.read_text()
        assert "SMTP_PASSWORD" not in content

    def test_toggle_password_reveals_text(self, app):
        assert app._pass_shown is False
        app._toggle_password()
        assert app._pass_shown is True
        assert app._pass_entry.cget("show") == ""

    def test_toggle_password_hides_again(self, app):
        app._toggle_password()
        app._toggle_password()
        assert app._pass_shown is False
        assert app._pass_entry.cget("show") == "•"

    def test_send_test_email_disables_button_and_starts_thread(self, app):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            app._send_test_email()
        assert str(app._test_btn.cget("state")) == "disabled"
        mock_thread.assert_called_once()

    def test_test_email_done_success_shows_info(self, app):
        from smtp_notifier import EmailResult
        result = EmailResult(sent=True)
        with patch("tkinter.messagebox.showinfo") as mock_info:
            app._test_email_done(result)
        mock_info.assert_called_once()
        assert str(app._test_btn.cget("state")) == "normal"

    def test_test_email_done_failure_shows_error(self, app):
        from smtp_notifier import EmailResult
        result = EmailResult(sent=False, error="Auth failed")
        with patch("tkinter.messagebox.showerror") as mock_err:
            app._test_email_done(result)
        mock_err.assert_called_once()
        assert "Auth failed" in mock_err.call_args[0][1]

    def test_cred_warn_hidden_when_credentials_present(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        fake_env.write_text("SMTP_USER=u@g.com\nSMTP_PASSWORD=pw\n")
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._refresh_cred_banner()
        # pack_info raises TclError if widget is not managed (i.e., pack_forget was called)
        import tkinter as tk
        try:
            app._cred_warn.pack_info()
            is_packed = True
        except tk.TclError:
            is_packed = False
        assert not is_packed

    def test_cred_warn_shown_when_credentials_missing(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / "empty.env"
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._refresh_cred_banner()
        import tkinter as tk
        try:
            app._cred_warn.pack_info()
            is_packed = True
        except tk.TclError:
            is_packed = False
        assert is_packed

    def test_check_first_run_switches_to_settings_when_no_creds(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / "empty.env"
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._check_first_run()
        assert app._nb.index("current") == app._nb.index(app._tab_settings)

    def test_check_first_run_stays_on_dashboard_when_creds_present(self, app, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        fake_env.write_text("SMTP_USER=u@g.com\nSMTP_PASSWORD=pw\n")
        import data_dir
        monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
        app._nb.select(app._tab_dash)
        app._check_first_run()
        assert app._nb.index("current") == app._nb.index(app._tab_dash)

    def test_load_credentials_ticks_smtp_checkbox_for_custom_host(self, app, fake_env):
        fake_env.write_text(
            "SMTP_USER=me@outlook.com\nSMTP_PASSWORD=pw\n"
            "SMTP_HOST=smtp-mail.outlook.com\nSMTP_PORT=587\n"
        )
        app._load_credentials_to_form()
        assert app._smtp_custom_var.get() is True
        assert app._smtp_host_var.get() == "smtp-mail.outlook.com"
        assert app._smtp_port_var.get() == "587"

    def test_load_credentials_does_not_tick_smtp_checkbox_for_gmail(self, app, fake_env):
        fake_env.write_text("SMTP_USER=me@gmail.com\nSMTP_PASSWORD=pw\n")
        app._load_credentials_to_form()
        assert app._smtp_custom_var.get() is False

    def test_save_credentials_writes_smtp_host_when_checkbox_ticked(self, app, fake_env):
        from dotenv import dotenv_values
        fake_env.touch()
        app._cred_user_var.set("me@outlook.com")
        app._cred_pass_var.set("mypassword")
        app._smtp_custom_var.set(True)
        app._smtp_host_var.set("smtp-mail.outlook.com")
        app._smtp_port_var.set("587")
        app._save_credentials()
        vals = dotenv_values(fake_env)
        assert vals["SMTP_USER"] == "me@outlook.com"
        assert vals["SMTP_HOST"] == "smtp-mail.outlook.com"
        assert vals["SMTP_PORT"] == "587"

    def test_save_credentials_omits_smtp_host_when_checkbox_unticked(self, app, fake_env):
        from dotenv import dotenv_values
        fake_env.touch()
        app._cred_user_var.set("me@gmail.com")
        app._cred_pass_var.set("mypassword")
        app._smtp_custom_var.set(False)
        app._save_credentials()
        vals = dotenv_values(fake_env)
        assert "SMTP_HOST" not in vals
        assert "SMTP_PORT" not in vals
