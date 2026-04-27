# Forecast Tab — 14-Night Weather Outlook

**Date:** 2026-04-27  
**Status:** Approved

## Overview

Add a new "Forecast" tab to the AstroAlert GUI showing a 14-night go/no-go outlook for a selected site. Clicking a night reveals a detail panel with the score breakdown and hourly imaging-window weather.

## Architecture & Data

### Weather fetch
Add `fetch_weather_range(site_key, lat, lon, days=14) -> list[tuple[date, WeatherResult]]` to `weather.py`. Open-Meteo supports 16-day forecasts on the same endpoint currently used; the only change is a wider `end_date`. One API call covers all 14 days.

### Seeing fetch
7timer.info forecasts ~7 days. Fetch what is available; nights beyond its range show "N/A" for the seeing sub-score. The total score for those nights is re-normalized from weather + moon only (two-factor weighting).

### Moon
`ephem`-based `get_moon_info()` works for any future date — all 14 nights receive a full moon score.

### Scoring
Each night's score is computed by calling the existing `score_night()` with the appropriate `target_date`. No changes to scorer logic.

### Threading & caching
Data is fetched in a background thread (same `threading.Thread(daemon=True)` pattern as the Dashboard). Results are cached per site for the session. Switching sites in the selector clears the cache and re-fetches. Clicking a row in the list does not re-fetch.

## UI Layout

### Tab placement
New "  Forecast  " tab inserted after "  Schedule  " and before "  Scoring  " in the notebook.

### Controls row
- Site selector combobox (same style and data source as Dashboard's `_site_combo`, but single-site only — no "All sites" option)
- "Load Forecast" button (Accent style); disabled while fetching, shows "Loading…"

### 14-night Treeview
`ttk.Treeview` with columns:

| Column  | Example       | Width | Anchor |
|---------|---------------|-------|--------|
| Date    | Mon Apr 28    | 130   | w      |
| Verdict | GO / no-go    | 80    | center |
| Score   | 74/100        | 80    | center |
| Clouds  | 42%           | 80    | center |
| Moon    | 31%           | 80    | center |

Row tags `go` (GO_CLR) and `nogo` (NOGO_CLR) color the Verdict cell. Rows with fetch errors get a `warn` tag (WARN_CLR) and show "—" for numeric fields.

### Detail panel
Hidden until a row is first selected, then permanently visible. Separated from the Treeview by a `ttk.Separator`.

Inside a `Card.TFrame`, two side-by-side sections:

**Left — Score breakdown**
- Total score (large, colored GO/NO-GO)
- Weather / Seeing / Moon sub-scores (with "N/A" for seeing beyond 7timer range)
- Warning list (same text the Dashboard produces)

**Right — Hourly imaging window**
- `tk.Text` in mono font, read-only
- Columns: Hour (UTC) · Clouds % · Wind km/h · Humidity %
- Covers 20:00–04:00 imaging window only (9 hours)
- If weather fetch failed for that night: single error line in WARN_CLR

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Weather API failure for a night | Row shows "—" in Score/Clouds; detail panel shows error message |
| Seeing data unavailable (beyond ~7 days) | Seeing sub-score shows "N/A"; total re-normalized from weather + moon |
| No sites configured | Tab body shows "No sites configured — add one in the Sites tab." |
| Network timeout during range fetch | Error banner below controls row; list remains empty; button re-enabled |

## Testing

### `test_weather.py`
Add `test_fetch_weather_range`: mock `requests.get` to return 14 days of hourly data; assert 14 `WeatherResult` objects returned, each with the correct date and non-empty `hours`.

### `test_gui.py`
Add smoke test: instantiate `AstroAlertApp`, assert the Forecast tab frame exists in the notebook without raising.

No new test files. Extend existing ones only.

## Out of Scope

- Exporting the 14-night forecast to CSV or email
- Showing multiple sites side-by-side in the Forecast tab
- Persisting the forecast cache across app restarts
