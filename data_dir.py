"""Platform-aware user data directory for AstroAlert."""
import platform
import shutil
import sys
from pathlib import Path

_APP = "AstroAlert"


def _compute() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        import os
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    d = base / _APP
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundled_sites() -> Path:
    """Return the path to the shipped sites.json (works frozen and dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "sites.json"
    return Path(__file__).parent / "sites.json"


DATA_DIR   = _compute()
ENV_FILE   = DATA_DIR / ".env"
SITES_FILE = DATA_DIR / "sites.json"

# Seed sites.json on first run so new users start with the example sites.
if not SITES_FILE.exists():
    src = _bundled_sites()
    if src.exists():
        shutil.copy(src, SITES_FILE)
