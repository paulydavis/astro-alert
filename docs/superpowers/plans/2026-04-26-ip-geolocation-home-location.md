# IP Geolocation — Auto-Detect Home Location Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add IP-based location detection to the Settings tab so the home location fields auto-fill on first launch and via a "Detect" button.

**Architecture:** A module-level `_detect_ip_location()` helper calls `ip-api.com/json/` and returns `(lat, lon, display)`. Three instance methods (`_do_ip_detect`, `_ip_detect_done`, `_ip_detect_error`) wire it to the GUI via background threads and `after(0, ...)`. Both entry points (button click and first launch) share the same thread worker.

**Tech Stack:** `requests` (already in requirements), `threading` (already used in gui.py), ip-api.com free JSON endpoint (no API key, plain HTTP required)

---

## File Structure

**Modify only:** `gui.py`, `test_gui.py`

- `gui.py` — add `_detect_ip_location()` module-level helper (~line 65); add `_home_status_var`, Detect button, and status label to `_build_settings_tab` (~lines 669, 679, 701); add `_do_ip_detect`, `_ip_detect_done`, `_ip_detect_error` methods (~line 822); extend `_check_first_run` (~line 868)
- `test_gui.py` — add `TestDetectIpLocation` class (helper tests) and extend `TestSettingsTab` with detect button and auto-launch tests

---

## Task 1: `_detect_ip_location()` helper

**Files:**
- Modify: `gui.py` (after `_osrm_drive_minutes`, ~line 64)
- Test: `test_gui.py` (new class `TestDetectIpLocation`)

- [ ] **Step 1: Write the failing tests**

Add this class to `test_gui.py` after the existing imports/fixtures section (after line 80):

```python
class TestDetectIpLocation:
    def test_returns_lat_lon_display_on_success(self):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "status": "success",
            "lat": 35.99,
            "lon": -78.89,
            "city": "Durham",
            "regionName": "North Carolina",
        }
        with patch("requests.get", return_value=fake):
            lat, lon, display = gui._detect_ip_location()
        assert lat == 35.99
        assert lon == -78.89
        assert display == "Durham, North Carolina"

    def test_raises_on_non_200(self):
        fake = MagicMock()
        fake.status_code = 429
        with patch("requests.get", return_value=fake):
            with pytest.raises(RuntimeError, match="HTTP 429"):
                gui._detect_ip_location()

    def test_raises_on_fail_status(self):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {"status": "fail", "message": "private range"}
        with patch("requests.get", return_value=fake):
            with pytest.raises(RuntimeError, match="Location not found"):
                gui._detect_ip_location()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest test_gui.py::TestDetectIpLocation -v
```

Expected: 3 failures — `AttributeError: module 'gui' has no attribute '_detect_ip_location'`

- [ ] **Step 3: Add `_detect_ip_location()` to gui.py**

Insert after `_osrm_drive_minutes` (after line 63, before the `# ──────` separator):

```python
def _detect_ip_location() -> tuple[float, float, str]:
    """Call ip-api.com and return (lat, lon, 'City, Region')."""
    import requests
    resp = requests.get(
        "http://ip-api.com/json/",
        params={"fields": "status,lat,lon,city,regionName"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError("Location not found")
    return float(data["lat"]), float(data["lon"]), f"{data['city']}, {data['regionName']}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest test_gui.py::TestDetectIpLocation -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: add _detect_ip_location() helper using ip-api.com"
```

---

## Task 2: Detect button and status label in Settings

**Files:**
- Modify: `gui.py` — `_build_settings_tab` (~lines 669, 679, 699) and new methods after `_save_home_location` (~line 822)
- Test: `test_gui.py` — extend `TestSettingsTab`

- [ ] **Step 1: Write the failing tests**

Add these methods to the `TestSettingsTab` class in `test_gui.py` (after the last existing test in that class):

```python
def test_home_detect_btn_exists(self, app):
    assert hasattr(app, "_home_detect_btn")

def test_home_status_var_exists(self, app):
    assert hasattr(app, "_home_status_var")

def test_ip_detect_done_populates_fields(self, app):
    app._ip_detect_done(35.99, -78.89, "Durham, North Carolina")
    assert app._home_lat_var.get() == "35.99000"
    assert app._home_lon_var.get() == "-78.89000"
    assert app._home_search_var.get() == "Durham, North Carolina"
    assert "Durham, North Carolina" in app._home_status_var.get()
    assert "Save" in app._home_status_var.get()

def test_ip_detect_error_sets_status(self, app):
    app._ip_detect_error("timeout")
    assert "try searching manually" in app._home_status_var.get()

def test_detect_button_starts_thread(self, app):
    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        app._detect_home_location()
    assert str(app._home_detect_btn.cget("state")) == "disabled"
    mock_thread.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest test_gui.py::TestSettingsTab::test_home_detect_btn_exists test_gui.py::TestSettingsTab::test_home_status_var_exists test_gui.py::TestSettingsTab::test_ip_detect_done_populates_fields test_gui.py::TestSettingsTab::test_ip_detect_error_sets_status test_gui.py::TestSettingsTab::test_detect_button_starts_thread -v
```

Expected: 5 failures

- [ ] **Step 3: Add `_home_status_var` to `_build_settings_tab`**

In `_build_settings_tab`, find the block that declares the StringVars (~line 666):

```python
self._home_geo_results: list[dict] = []
self._home_search_var = tk.StringVar()
self._home_lat_var    = tk.StringVar()
self._home_lon_var    = tk.StringVar()
```

Replace with:

```python
self._home_geo_results: list[dict] = []
self._home_search_var  = tk.StringVar()
self._home_lat_var     = tk.StringVar()
self._home_lon_var     = tk.StringVar()
self._home_status_var  = tk.StringVar()
```

- [ ] **Step 4: Add Detect button to home_card**

Find the Search button grid call (~line 677):

```python
self._home_search_btn = ttk.Button(home_card, text="Search", width=8,
                                    command=self._search_home_location)
self._home_search_btn.grid(row=0, column=2, padx=(8, 16), pady=8)
```

Replace with:

```python
self._home_search_btn = ttk.Button(home_card, text="Search", width=8,
                                    command=self._search_home_location)
self._home_search_btn.grid(row=0, column=2, padx=(8, 4), pady=8)
self._home_detect_btn = ttk.Button(home_card, text="Detect", width=8,
                                    command=self._detect_home_location)
self._home_detect_btn.grid(row=0, column=3, padx=(0, 16), pady=8)
```

- [ ] **Step 5: Add status label below Save button**

Find the home_btn_row block (~line 698):

```python
home_btn_row = ttk.Frame(inner)
home_btn_row.pack(pady=(14, 24))
ttk.Button(home_btn_row, text="Save Home Location", style="Accent.TButton",
           command=self._save_home_location).pack()
```

Replace with:

```python
home_btn_row = ttk.Frame(inner)
home_btn_row.pack(pady=(14, 4))
ttk.Button(home_btn_row, text="Save Home Location", style="Accent.TButton",
           command=self._save_home_location).pack()
ttk.Label(inner, textvariable=self._home_status_var,
          style="Dim.TLabel").pack(pady=(4, 24))
```

- [ ] **Step 6: Add the three new methods after `_save_home_location`**

Find the end of `_save_home_location` (~line 820) and insert after it:

```python
def _detect_home_location(self):
    self._home_detect_btn.configure(state="disabled", text="…")
    threading.Thread(target=self._do_ip_detect, daemon=True).start()

def _do_ip_detect(self):
    try:
        lat, lon, display = _detect_ip_location()
        self.after(0, self._ip_detect_done, lat, lon, display)
    except Exception as e:
        self.after(0, self._ip_detect_error, str(e))

def _ip_detect_done(self, lat: float, lon: float, display: str):
    self._home_detect_btn.configure(state="normal", text="Detect")
    self._home_search_var.set(display)
    self._home_lat_var.set(f"{lat:.5f}")
    self._home_lon_var.set(f"{lon:.5f}")
    self._home_status_var.set(
        f"Location detected: {display} — click Save to confirm"
    )

def _ip_detect_error(self, _msg: str):
    self._home_detect_btn.configure(state="normal", text="Detect")
    self._home_status_var.set(
        "Could not detect location — try searching manually"
    )
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
python3 -m pytest test_gui.py::TestSettingsTab -v
```

Expected: all tests in TestSettingsTab pass

- [ ] **Step 8: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: add Detect button and status label to home location card"
```

---

## Task 3: Auto-detect on first launch

**Files:**
- Modify: `gui.py` — `_check_first_run` (~line 862)
- Test: `test_gui.py` — extend `TestSettingsTab`

- [ ] **Step 1: Write the failing tests**

Add these two methods to `TestSettingsTab` in `test_gui.py`:

```python
def test_check_first_run_spawns_detect_when_home_absent(self, app, fake_env, monkeypatch):
    import data_dir
    monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)  # fake_env is empty
    started_targets = []
    def mock_thread(*a, **kw):
        m = MagicMock()
        m.start.side_effect = lambda: started_targets.append(kw.get("target"))
        return m
    with patch("threading.Thread", side_effect=mock_thread):
        app._check_first_run()
    assert app._do_ip_detect in started_targets

def test_check_first_run_skips_detect_when_home_set(self, app, fake_env, monkeypatch):
    import data_dir
    fake_env.write_text("HOME_LAT=35.99\nHOME_LON=-78.89\n")
    monkeypatch.setattr(data_dir, "ENV_FILE", fake_env)
    started_targets = []
    def mock_thread(*a, **kw):
        m = MagicMock()
        m.start.side_effect = lambda: started_targets.append(kw.get("target"))
        return m
    with patch("threading.Thread", side_effect=mock_thread):
        app._check_first_run()
    assert app._do_ip_detect not in started_targets
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest test_gui.py::TestSettingsTab::test_check_first_run_spawns_detect_when_home_absent test_gui.py::TestSettingsTab::test_check_first_run_skips_detect_when_home_set -v
```

Expected: 2 failures

- [ ] **Step 3: Extend `_check_first_run`**

Find `_check_first_run` (~line 862):

```python
def _check_first_run(self):
    from data_dir import ENV_FILE
    from dotenv import dotenv_values
    vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
    smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        self._nb.select(self._tab_settings)
```

Replace with:

```python
def _check_first_run(self):
    from data_dir import ENV_FILE
    from dotenv import dotenv_values
    vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
    smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        self._nb.select(self._tab_settings)
    if not vals.get("HOME_LAT") or not vals.get("HOME_LON"):
        threading.Thread(target=self._do_ip_detect, daemon=True).start()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest test_gui.py::TestSettingsTab -v
```

Expected: all TestSettingsTab tests pass

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m pytest test_*.py -q
```

Expected: all tests pass, no regressions

- [ ] **Step 6: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: auto-detect home location via IP on first launch"
```
