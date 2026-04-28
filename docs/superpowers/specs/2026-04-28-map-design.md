# Map Feature Design

## Overview

Embed an interactive map in the Sites tab as a split view: site list on the left, OpenStreetMap map on the right. Uses `tkintermapview` — a purpose-built Tkinter widget with built-in tile caching and marker support. No API key required.

## Architecture & Layout

The Sites tab `ttk.PanedWindow` (horizontal) replaces the current simple list frame:

- **Left pane (≈35%)**: existing site list `ttk.Treeview`, unchanged
- **Right pane (≈65%)**: `tkintermapview.TkinterMapView` widget filling available space, OSM tiles

Sash is draggable. No new files — all map code lives in `gui.py` inside the Sites tab build method and helpers.

On load, the map frames all site pins via `fit_bounding_box()`. Default zoom when no sites: continental US (39°N, 95°W, zoom 4).

## Components & Data Flow

### Site list → map

On app load and whenever sites change (add, edit, delete):
1. Clear all existing markers
2. Call `map_widget.set_marker(lat, lon, text=name)` for each site in `self.sites`

Clicking a marker shows a popup with:
- Site name
- Bortle class
- "Go to Forecast" button — switches to Forecast tab and selects that site in the dropdown

### Empty map click → Add Site

`map_widget.add_left_click_map_command(callback)` fires with `(lat, lon)`. Opens the existing Add Site dialog with lat/lon fields pre-filled. On save, the new site gets a pin immediately.

### Map initialization

- Multiple sites: `map_widget.fit_bounding_box(max_lat, min_lat, max_lon, min_lon)`
- Single site: `map_widget.set_position(lat, lon, zoom=10)`
- No sites: `map_widget.set_position(39.0, -95.0, zoom=4)`

Markers are cleared and redrawn on every site list change. No persistent map state — all derived from `sites.json`.

## Error Handling

| Scenario | Behavior |
|---|---|
| `tkintermapview` not installed | Right pane shows label: "Map requires tkintermapview — run: pip install tkintermapview" |
| No internet / tile load failure | Tiles show as gray squares; pins and interactions still work (tkintermapview handles gracefully) |
| No sites | Map renders at continental US default, empty list on left |
| Single site | `set_position(lat, lon, zoom=10)` instead of `fit_bounding_box` |
| Site with missing lat/lon | Skip marker silently |
| "Go to Forecast" with stale site name | Switch to Forecast tab; if site not in dropdown, let user pick manually |

## Pin Style

Neutral color (default `tkintermapview` marker) — no GO/NO-GO status on map. Status belongs on the Forecast tab.

## Dependencies

- `tkintermapview` — add to `requirements.txt`

## Out of Scope

- GO/NO-GO color-coded pins
- Satellite/terrain tile layers
- Clustering for dense pin groups
- Offline tile pre-download
