"""Tests for scheduler_setup.py — cross-platform cron / Task Scheduler."""

from unittest.mock import MagicMock, patch, call

import pytest

import scheduler_setup


# ── _read_crontab / _write_crontab ────────────────────────────────────────────

class TestReadCrontab:
    def test_returns_stdout_on_success(self):
        result = MagicMock(returncode=0, stdout="0 * * * * myjob\n")
        with patch("subprocess.run", return_value=result):
            text = scheduler_setup._read_crontab()
        assert "myjob" in text

    def test_returns_empty_string_when_no_crontab(self):
        result = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=result):
            text = scheduler_setup._read_crontab()
        assert text == ""

    def test_passes_correct_crontab_args(self):
        result = MagicMock(returncode=0, stdout="")
        with patch("subprocess.run", return_value=result) as mock_run:
            scheduler_setup._read_crontab()
        mock_run.assert_called_once_with(
            ["crontab", "-l"], capture_output=True, text=True
        )


class TestWriteCrontab:
    def test_pipes_text_to_crontab(self):
        with patch("subprocess.run") as mock_run:
            scheduler_setup._write_crontab("0 18 * * * job\n")
        mock_run.assert_called_once_with(
            ["crontab", "-"], input="0 18 * * * job\n", text=True, check=True
        )


# ── _cron_status ──────────────────────────────────────────────────────────────

class TestCronStatus:
    def test_installed_when_lines_found(self):
        cron = "0 18 * * * python3 astro_alert.py --tomorrow\n0 14 * * * python3 astro_alert.py --only-if-go\n"
        with patch("scheduler_setup._read_crontab", return_value=cron):
            installed, detail = scheduler_setup._cron_status()
        assert installed is True
        assert "astro_alert.py" in detail

    def test_not_installed_when_no_matching_lines(self):
        with patch("scheduler_setup._read_crontab", return_value="0 0 * * * other_job\n"):
            installed, detail = scheduler_setup._cron_status()
        assert installed is False
        assert detail == ""

    def test_not_installed_on_empty_crontab(self):
        with patch("scheduler_setup._read_crontab", return_value=""):
            installed, _ = scheduler_setup._cron_status()
        assert installed is False

    def test_detail_contains_both_cron_lines(self):
        cron = "0 18 * * * python3 astro_alert.py --tomorrow\n0 14 * * * python3 astro_alert.py --only-if-go\n"
        with patch("scheduler_setup._read_crontab", return_value=cron):
            _, detail = scheduler_setup._cron_status()
        assert "--tomorrow" in detail
        assert "--only-if-go" in detail


# ── _cron_install ─────────────────────────────────────────────────────────────

class TestCronInstall:
    def test_adds_two_astro_lines(self):
        written = []
        with patch("scheduler_setup._read_crontab", return_value=""), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        lines = [l for l in written[0].splitlines() if l.strip()]
        assert sum(1 for l in lines if "astro_alert.py" in l) == 2

    def test_adds_tomorrow_job(self):
        written = []
        with patch("scheduler_setup._read_crontab", return_value=""), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        assert any("--tomorrow" in l for l in written[0].splitlines())

    def test_adds_only_if_go_job(self):
        written = []
        with patch("scheduler_setup._read_crontab", return_value=""), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        assert any("--only-if-go" in l for l in written[0].splitlines())

    def test_preserves_unrelated_cron_jobs(self):
        existing = "0 * * * * /usr/bin/backup.sh\n"
        written = []
        with patch("scheduler_setup._read_crontab", return_value=existing), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        assert "backup.sh" in written[0]

    def test_replaces_existing_astro_lines(self):
        existing = "0 18 * * * python3 astro_alert.py --tomorrow\nother\n"
        written = []
        with patch("scheduler_setup._read_crontab", return_value=existing), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        count = written[0].count("astro_alert.py")
        assert count == 2  # old one removed, two new ones added

    def test_scheduled_at_correct_times(self):
        written = []
        with patch("scheduler_setup._read_crontab", return_value=""), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_install()
        lines = [l for l in written[0].splitlines() if "astro_alert.py" in l]
        times = [l.split()[1] for l in lines]  # hour field
        assert "18" in times  # 6pm job
        assert "14" in times  # 2pm job


# ── _cron_uninstall ───────────────────────────────────────────────────────────

class TestCronUninstall:
    def test_removes_astro_alert_lines(self):
        existing = "0 18 * * * python3 astro_alert.py --tomorrow\n0 * * * * other_job\n"
        written = []
        with patch("scheduler_setup._read_crontab", return_value=existing), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_uninstall()
        assert "astro_alert.py" not in written[0]

    def test_preserves_other_cron_jobs(self):
        existing = "0 18 * * * python3 astro_alert.py --tomorrow\n0 * * * * other_job\n"
        written = []
        with patch("scheduler_setup._read_crontab", return_value=existing), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_uninstall()
        assert "other_job" in written[0]

    def test_no_op_when_nothing_installed(self):
        existing = "0 * * * * other_job\n"
        written = []
        with patch("scheduler_setup._read_crontab", return_value=existing), \
             patch("scheduler_setup._write_crontab", side_effect=written.append):
            scheduler_setup._cron_uninstall()
        assert "other_job" in written[0]


# ── install_schedule / uninstall_schedule ─────────────────────────────────────

class TestInstallSchedule:
    def test_calls_cron_install_on_darwin(self):
        with patch("scheduler_setup._OS", "Darwin"), \
             patch("scheduler_setup._cron_install") as mock:
            scheduler_setup.install_schedule()
        mock.assert_called_once()

    def test_calls_cron_install_on_linux(self):
        with patch("scheduler_setup._OS", "Linux"), \
             patch("scheduler_setup._cron_install") as mock:
            scheduler_setup.install_schedule()
        mock.assert_called_once()

    def test_calls_win_install_on_windows(self):
        with patch("scheduler_setup._OS", "Windows"), \
             patch("scheduler_setup._win_install") as mock:
            scheduler_setup.install_schedule()
        mock.assert_called_once()

    def test_raises_on_unsupported_platform(self):
        with patch("scheduler_setup._OS", "FreeBSD"):
            with pytest.raises(NotImplementedError, match="FreeBSD"):
                scheduler_setup.install_schedule()


class TestUninstallSchedule:
    def test_calls_cron_uninstall_on_darwin(self):
        with patch("scheduler_setup._OS", "Darwin"), \
             patch("scheduler_setup._cron_uninstall") as mock:
            scheduler_setup.uninstall_schedule()
        mock.assert_called_once()

    def test_calls_cron_uninstall_on_linux(self):
        with patch("scheduler_setup._OS", "Linux"), \
             patch("scheduler_setup._cron_uninstall") as mock:
            scheduler_setup.uninstall_schedule()
        mock.assert_called_once()

    def test_calls_win_uninstall_on_windows(self):
        with patch("scheduler_setup._OS", "Windows"), \
             patch("scheduler_setup._win_uninstall") as mock:
            scheduler_setup.uninstall_schedule()
        mock.assert_called_once()

    def test_raises_on_unsupported_platform(self):
        with patch("scheduler_setup._OS", "FreeBSD"):
            with pytest.raises(NotImplementedError):
                scheduler_setup.uninstall_schedule()


# ── get_schedule_status ───────────────────────────────────────────────────────

class TestGetScheduleStatus:
    def test_delegates_to_cron_on_darwin(self):
        with patch("scheduler_setup._OS", "Darwin"), \
             patch("scheduler_setup._cron_status", return_value=(True, "detail")) as mock:
            installed, detail = scheduler_setup.get_schedule_status()
        mock.assert_called_once()
        assert installed is True
        assert detail == "detail"

    def test_delegates_to_cron_on_linux(self):
        with patch("scheduler_setup._OS", "Linux"), \
             patch("scheduler_setup._cron_status", return_value=(False, "")) as mock:
            installed, _ = scheduler_setup.get_schedule_status()
        mock.assert_called_once()
        assert installed is False

    def test_delegates_to_win_on_windows(self):
        with patch("scheduler_setup._OS", "Windows"), \
             patch("scheduler_setup._win_status", return_value=(True, "tasks registered")) as mock:
            installed, detail = scheduler_setup.get_schedule_status()
        mock.assert_called_once()
        assert installed is True

    def test_returns_false_on_unsupported_platform(self):
        with patch("scheduler_setup._OS", "FreeBSD"):
            installed, detail = scheduler_setup.get_schedule_status()
        assert installed is False
        assert "Unsupported" in detail


# ── Windows Task Scheduler (mocked) ──────────────────────────────────────────

class TestWinInstall:
    def test_creates_two_tasks(self):
        mock_result = MagicMock(returncode=0)
        with patch("scheduler_setup._schtasks", return_value=mock_result) as mock:
            scheduler_setup._win_install()
        assert mock.call_count == 2

    def test_creates_6pm_task(self):
        mock_result = MagicMock(returncode=0)
        calls = []
        with patch("scheduler_setup._schtasks",
                   side_effect=lambda *a: calls.append(a) or mock_result):
            scheduler_setup._win_install()
        # args: ("/create", "/f", "/tn", name, "/tr", cmd, ...)
        task_names = [args[args.index("/tn") + 1] for args in calls]
        assert "AstroAlert-6pm" in task_names

    def test_creates_2pm_task(self):
        mock_result = MagicMock(returncode=0)
        calls = []
        with patch("scheduler_setup._schtasks",
                   side_effect=lambda *a: calls.append(a) or mock_result):
            scheduler_setup._win_install()
        task_names = [args[args.index("/tn") + 1] for args in calls]
        assert "AstroAlert-2pm" in task_names

    def test_raises_on_schtasks_failure(self):
        mock_result = MagicMock(returncode=1, stderr="Access denied")
        with patch("scheduler_setup._schtasks", return_value=mock_result):
            with pytest.raises(RuntimeError, match="schtasks failed"):
                scheduler_setup._win_install()


class TestWinStatus:
    def test_installed_when_query_succeeds(self):
        mock_result = MagicMock(returncode=0)
        with patch("scheduler_setup._schtasks", return_value=mock_result):
            installed, _ = scheduler_setup._win_status()
        assert installed is True

    def test_not_installed_when_query_fails(self):
        mock_result = MagicMock(returncode=1)
        with patch("scheduler_setup._schtasks", return_value=mock_result):
            installed, _ = scheduler_setup._win_status()
        assert installed is False


class TestSchtasksHelper:
    def test_prepends_schtasks_command(self):
        result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=result) as mock_run:
            scheduler_setup._schtasks("/query", "/tn", "MyTask")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "schtasks"
        assert "/query" in cmd
        assert "MyTask" in cmd


class TestWinUninstall:
    def test_deletes_both_tasks(self):
        result = MagicMock(returncode=0)
        calls = []
        with patch("scheduler_setup._schtasks",
                   side_effect=lambda *a: calls.append(a) or result):
            scheduler_setup._win_uninstall()
        assert len(calls) == 2
        task_names = [args[args.index("/tn") + 1] for args in calls]
        assert "AstroAlert-6pm" in task_names
        assert "AstroAlert-2pm" in task_names
