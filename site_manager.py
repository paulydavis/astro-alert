"""Site management for astro_alert — loads/saves sites.json."""

import json
from pathlib import Path
from typing import Optional

SITES_FILE = Path(__file__).parent / "sites.json"


class Site:
    def __init__(self, key: str, data: dict):
        self.key = key
        self.name: str = data["name"]
        self.lat: float = data["lat"]
        self.lon: float = data["lon"]
        self.elevation_m: float = data["elevation_m"]
        self.bortle: int = data["bortle"]
        self.timezone: str = data["timezone"]
        self.drive_min: Optional[int] = data.get("drive_min")
        self.notes: str = data.get("notes", "")

    def __repr__(self) -> str:
        return (
            f"Site({self.key!r}, lat={self.lat}, lon={self.lon}, "
            f"bortle={self.bortle}, tz={self.timezone!r})"
        )


def _load_raw() -> dict:
    try:
        return json.loads(SITES_FILE.read_text())
    except FileNotFoundError:
        raise FileNotFoundError(f"sites.json not found at {SITES_FILE}")
    except json.JSONDecodeError as e:
        raise ValueError(f"sites.json is invalid JSON: {e}")


def _save_raw(data: dict) -> None:
    SITES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def get_active_site(override: Optional[str] = None) -> Site:
    """Return the active Site, optionally overriding with a site key."""
    data = _load_raw()
    key = override if override is not None else data.get("active_site")
    if not key:
        raise ValueError("No active_site set in sites.json and no --site override given.")
    sites = data.get("sites", {})
    if key not in sites:
        known = ", ".join(sites) or "(none)"
        raise KeyError(f"Site {key!r} not found. Known sites: {known}")
    return Site(key, sites[key])


def list_sites() -> list[tuple[str, Site, bool]]:
    """Return [(key, Site, is_active), ...] sorted by key."""
    data = _load_raw()
    active_key = data.get("active_site")
    return [
        (key, Site(key, site_data), key == active_key)
        for key, site_data in sorted(data.get("sites", {}).items())
    ]


def add_site(
    key: str,
    name: str,
    lat: float,
    lon: float,
    elevation_m: float,
    bortle: int,
    timezone: str,
    set_active: bool = False,
) -> Site:
    """Add a new site (or overwrite an existing one) and optionally make it active."""
    data = _load_raw()
    sites = data.setdefault("sites", {})
    sites[key] = {
        "name": name,
        "lat": lat,
        "lon": lon,
        "elevation_m": elevation_m,
        "bortle": bortle,
        "timezone": timezone,
    }
    if set_active:
        data["active_site"] = key
    _save_raw(data)
    return Site(key, sites[key])


def set_active_site(key: str) -> None:
    """Set the active site by key, raising KeyError if not found."""
    data = _load_raw()
    if key not in data.get("sites", {}):
        known = ", ".join(data.get("sites", {})) or "(none)"
        raise KeyError(f"Site {key!r} not found. Known sites: {known}")
    data["active_site"] = key
    _save_raw(data)
