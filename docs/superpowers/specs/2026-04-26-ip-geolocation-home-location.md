# IP Geolocation — Auto-Detect Home Location

## Goal

Automatically detect the user's approximate location via IP geolocation and use it to pre-fill the Home Location fields in Settings, reducing friction for first-time setup.

## Architecture

A single module-level helper function calls `ip-api.com/json/` in a background thread. The GUI wires it into two places: a "Detect" button in the Settings home location card, and an automatic first-launch check in `App.__init__`. No new files, no new dependencies (`requests` is already installed).

## Tech Stack

- `ip-api.com` free JSON endpoint (no API key, plain HTTP required)
- `requests` (already in `requirements.txt`)
- `threading.Thread` (already used throughout `gui.py`)

---

## Feature Details

### Helper function — `_detect_ip_location()`

Module-level function in `gui.py`.

- Makes a GET request to `http://ip-api.com/json/?fields=lat,lon,city,regionName`
- Returns `(lat: float, lon: float, display: str)` where `display` is `"City, Region"` (e.g. `"Durham, North Carolina"`)
- Raises `RuntimeError` with a human-readable message on HTTP error, non-200 status, or `status != "success"` in the response body

### Detect button

Added to the home location card in `_build_settings_tab`, alongside the existing Search button.

- Label: `"Detect"`
- On click: disables itself (`text="…"`), spawns a daemon thread calling `_detect_ip_location()`
- On success (via `after(0, ...)`): populates `_home_search_var`, `_home_lat_var`, `_home_lon_var`; sets status label to `"Location detected: {display} — click Save to confirm"`; re-enables button
- On failure: sets status label to `"Could not detect location — try searching manually"`; re-enables button

### Status label

A `ttk.Label` below the "Save Home Location" button, bound to `_home_status_var = tk.StringVar()`.

- Style: `"Dim.TLabel"` (matches existing secondary text style)
- Starts empty; updated on each detect attempt (replaces previous message, never stacks)

### Auto-detect on first launch

In `App.__init__`, after the window is built, check if `HOME_LAT` and `HOME_LON` are both absent from `.env`. If so, spawn a daemon thread to run the same detection.

- On success: populates fields and sets status label (same as button flow)
- On failure: silent — no error shown, user can use Search or Detect button manually
- Runs only when home location is completely absent (not when it's set but user is editing)

## Error Handling

- Network failure → `RuntimeError("Network error: <detail>")` → button flow shows status message; first-launch flow is silent
- Non-200 HTTP → `RuntimeError("HTTP <status>")` → same
- `status != "success"` in response → `RuntimeError("Location not found")` → same
- All errors are caught at the call site; the app never crashes due to detection failure

## Testing

In `test_gui.py`, mock `requests.get` to return a fake ip-api.com response `{"status": "success", "lat": 35.99, "lon": -78.89, "city": "Durham", "regionName": "North Carolina"}` and verify:

- `_detect_ip_location()` returns `(35.99, -78.89, "Durham, North Carolina")`
- Detect button populates fields and sets the correct status message
- Detect button shows error status on HTTP failure
- Auto-detect on first launch populates fields when HOME_LAT/HOME_LON absent
- Auto-detect on first launch is skipped when HOME_LAT/HOME_LON already set
