"""Platform-aware user data directory for AstroAlert."""
import platform
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


DATA_DIR   = _compute()
ENV_FILE   = DATA_DIR / ".env"
SITES_FILE = DATA_DIR / "sites.json"
