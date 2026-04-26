"""Cross-platform scheduler setup for Astro Alert.

Installs two daily jobs:
  6:00 PM — astro_alert.py --tomorrow   (always sends, for planning the next night)
  2:00 PM — astro_alert.py --only-if-go (sends only when a site scores GO tonight)

macOS / Linux: writes crontab entries.
Windows:       creates Task Scheduler tasks via schtasks.
"""

import platform
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
SCRIPT = str(Path(__file__).parent / "astro_alert.py")
LOG    = str(Path(__file__).parent / "astro_alert.log")

_CRON_TAG  = "astro_alert.py"
_WIN_TASKS = ("AstroAlert-6pm", "AstroAlert-2pm")
_OS        = platform.system()


def install_schedule() -> None:
    if _OS in ("Darwin", "Linux"):
        _cron_install()
    elif _OS == "Windows":
        _win_install()
    else:
        raise NotImplementedError(f"Unsupported platform: {_OS}")


def uninstall_schedule() -> None:
    if _OS in ("Darwin", "Linux"):
        _cron_uninstall()
    elif _OS == "Windows":
        _win_uninstall()
    else:
        raise NotImplementedError(f"Unsupported platform: {_OS}")


def get_schedule_status() -> tuple[bool, str]:
    """Return (is_installed, detail_string)."""
    if _OS in ("Darwin", "Linux"):
        return _cron_status()
    elif _OS == "Windows":
        return _win_status()
    return False, f"Unsupported platform: {_OS}"


# ── cron (macOS / Linux) ──────────────────────────────────────────────────────

def _cron_lines() -> list[str]:
    return [
        f'0 18 * * * "{PYTHON}" "{SCRIPT}" --tomorrow >> "{LOG}" 2>&1',
        f'0 14 * * * "{PYTHON}" "{SCRIPT}" --only-if-go >> "{LOG}" 2>&1',
    ]


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def _write_crontab(text: str) -> None:
    subprocess.run(["crontab", "-"], input=text, text=True, check=True)


def _cron_install() -> None:
    kept = [l for l in _read_crontab().splitlines() if _CRON_TAG not in l]
    kept.extend(_cron_lines())
    _write_crontab("\n".join(kept) + "\n")


def _cron_uninstall() -> None:
    kept = [l for l in _read_crontab().splitlines() if _CRON_TAG not in l]
    _write_crontab("\n".join(kept) + "\n")


def _cron_status() -> tuple[bool, str]:
    found = [l for l in _read_crontab().splitlines() if _CRON_TAG in l]
    return bool(found), "\n".join(found)


# ── Windows Task Scheduler ────────────────────────────────────────────────────

def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks"] + list(args), capture_output=True, text=True)


def _win_install() -> None:
    jobs = [
        ("AstroAlert-6pm", "--tomorrow",   "18:00"),
        ("AstroAlert-2pm", "--only-if-go", "14:00"),
    ]
    for name, flag, start_time in jobs:
        cmd = f'"{PYTHON}" "{SCRIPT}" {flag}'
        result = _schtasks("/create", "/f", "/tn", name, "/tr", cmd,
                           "/sc", "DAILY", "/st", start_time)
        if result.returncode != 0:
            raise RuntimeError(f"schtasks failed for {name}: {result.stderr.strip()}")


def _win_uninstall() -> None:
    for name in _WIN_TASKS:
        _schtasks("/delete", "/f", "/tn", name)


def _win_status() -> tuple[bool, str]:
    result = _schtasks("/query", "/tn", "AstroAlert-6pm", "/fo", "LIST")
    if result.returncode == 0:
        return True, "AstroAlert-6pm and AstroAlert-2pm registered in Task Scheduler."
    return False, "No Astro Alert tasks found in Task Scheduler."
