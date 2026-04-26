"""Tests for site_manager.py."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

import site_manager as sm
from site_manager import Site, get_active_site, list_sites, add_site, set_active_site


MINIMAL = {
    "active_site": "home",
    "sites": {
        "home": {
            "name": "Home",
            "lat": 37.0,
            "lon": -122.0,
            "elevation_m": 100,
            "bortle": 6,
            "timezone": "America/Los_Angeles",
        },
        "dark": {
            "name": "Dark Field",
            "lat": 36.5,
            "lon": -121.5,
            "elevation_m": 500,
            "bortle": 3,
            "timezone": "America/Los_Angeles",
        },
    },
}


@pytest.fixture()
def sites_file(tmp_path, monkeypatch):
    """Redirect SITES_FILE to a temp file pre-populated with MINIMAL data."""
    path = tmp_path / "sites.json"
    path.write_text(json.dumps(MINIMAL, indent=2))
    monkeypatch.setattr(sm, "SITES_FILE", path)
    return path


# --- Site dataclass ----------------------------------------------------------

def test_site_attributes(sites_file):
    site = get_active_site()
    assert site.key == "home"
    assert site.name == "Home"
    assert site.lat == 37.0
    assert site.lon == -122.0
    assert site.elevation_m == 100
    assert site.bortle == 6
    assert site.timezone == "America/Los_Angeles"


# --- get_active_site ---------------------------------------------------------

def test_get_active_site_default(sites_file):
    site = get_active_site()
    assert site.key == "home"


def test_get_active_site_override(sites_file):
    site = get_active_site(override="dark")
    assert site.key == "dark"
    assert site.bortle == 3


def test_get_active_site_unknown_key(sites_file):
    with pytest.raises(KeyError, match="'ghost'"):
        get_active_site(override="ghost")


def test_get_active_site_no_active_set(sites_file):
    data = json.loads(sites_file.read_text())
    del data["active_site"]
    sites_file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="No active_site"):
        get_active_site()


# --- list_sites --------------------------------------------------------------

def test_list_sites_returns_all(sites_file):
    entries = list_sites()
    keys = [k for k, _, _ in entries]
    assert set(keys) == {"home", "dark"}


def test_list_sites_marks_active(sites_file):
    entries = list_sites()
    active = [(k, active) for k, _, active in entries]
    assert ("home", True) in active
    assert ("dark", False) in active


def test_list_sites_sorted(sites_file):
    entries = list_sites()
    keys = [k for k, _, _ in entries]
    assert keys == sorted(keys)


# --- add_site ----------------------------------------------------------------

def test_add_site_new(sites_file):
    site = add_site(
        key="rooftop",
        name="Rooftop",
        lat=37.8,
        lon=-122.3,
        elevation_m=20,
        bortle=8,
        timezone="America/Los_Angeles",
    )
    assert site.key == "rooftop"
    data = json.loads(sites_file.read_text())
    assert "rooftop" in data["sites"]
    assert data["active_site"] == "home"  # unchanged


def test_add_site_set_active(sites_file):
    add_site(
        key="rooftop",
        name="Rooftop",
        lat=37.8,
        lon=-122.3,
        elevation_m=20,
        bortle=8,
        timezone="America/Los_Angeles",
        set_active=True,
    )
    data = json.loads(sites_file.read_text())
    assert data["active_site"] == "rooftop"


def test_add_site_overwrites_existing(sites_file):
    add_site(
        key="home",
        name="Home Updated",
        lat=37.1,
        lon=-122.1,
        elevation_m=110,
        bortle=7,
        timezone="America/Los_Angeles",
    )
    data = json.loads(sites_file.read_text())
    assert data["sites"]["home"]["name"] == "Home Updated"
    assert data["sites"]["home"]["bortle"] == 7


# --- set_active_site ---------------------------------------------------------

def test_set_active_site(sites_file):
    set_active_site("dark")
    data = json.loads(sites_file.read_text())
    assert data["active_site"] == "dark"


def test_set_active_site_unknown(sites_file):
    with pytest.raises(KeyError, match="'nowhere'"):
        set_active_site("nowhere")


# --- file errors -------------------------------------------------------------

def test_missing_sites_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SITES_FILE", tmp_path / "nonexistent.json")
    with pytest.raises(FileNotFoundError):
        get_active_site()


def test_invalid_json(sites_file):
    sites_file.write_text("{ not valid json")
    with pytest.raises(ValueError, match="invalid JSON"):
        get_active_site()
