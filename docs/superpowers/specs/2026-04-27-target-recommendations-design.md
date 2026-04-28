# Target Recommendations Design

## Goal

For each GO night in the 14-night Forecast tab and in the HTML email, show up to 10 recommended deep-sky objects that are well-placed that night — ranked by peak altitude, filtered to objects actually visible during the imaging window.

## Architecture

Three components:

1. **`targets.json`** — static curated list of ~100 popular DSOs
2. **`target_recommender.py`** — visibility computation using ephem
3. **GUI + email integration** — render results in the Forecast detail panel and HTML email

No new dependencies. `ephem` is already used for sun/moon calculations.

---

## Component 1: `targets.json`

Stored at the project root alongside `sites.json`.

Each entry:

```json
{
  "name": "M42",
  "common_name": "Orion Nebula",
  "type": "Emission Nebula",
  "ra": "05 35 17",
  "dec": "-05 23 28",
  "magnitude": 4.0,
  "size_arcmin": 85,
  "description": "Brightest nebula in the sky; superb in any conditions"
}
```

**Fields:**
- `name` — Messier or NGC/IC designation (e.g. `"M31"`, `"NGC 7293"`)
- `common_name` — popular name (e.g. `"Andromeda Galaxy"`)
- `type` — one of: `Galaxy`, `Emission Nebula`, `Reflection Nebula`, `Planetary Nebula`, `Supernova Remnant`, `Open Cluster`, `Globular Cluster`, `Double Star`
- `ra` — J2000 right ascension as string `"HH MM SS"`
- `dec` — J2000 declination as string `"±DD MM SS"`
- `magnitude` — visual magnitude (float)
- `size_arcmin` — longest axis in arcminutes (float)
- `description` — one-line imaging note

**Coverage:** ~100 objects spanning all seasons, all types, all magnitudes suitable for visual/imaging interest. Messier catalog (~110 objects, subset excluding duplicates) plus popular NGC/IC targets: Veil Nebula, Horsehead Nebula, Iris Nebula, Triangulum Galaxy (M33), Helix Nebula, Crab Nebula, etc.

---

## Component 2: `target_recommender.py`

### Public API

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class TargetResult:
    name: str
    common_name: str
    type: str
    magnitude: float
    size_arcmin: float
    description: str
    peak_alt_deg: float        # highest altitude reached during imaging window (degrees)
    hours_visible: float       # hours above min_alt_deg during imaging window
    transit_utc: Optional[datetime]  # UTC time of peak altitude (None if not in window)


def get_nightly_targets(
    lat: float,
    lon: float,
    imaging_window: set[datetime],   # UTC datetimes, one per hour
    min_alt_deg: float = 25.0,
    min_hours: float = 2.0,
    max_results: int = 10,
) -> list[TargetResult]:
    ...
```

### Logic

1. Load `targets.json` from the same directory as the module.
2. For each target, create an `ephem.FixedBody` from its RA/Dec.
3. For each UTC hour in `imaging_window`, compute the body's altitude at that time and location.
4. Record `peak_alt_deg` (max altitude seen), `hours_visible` (count of hours above `min_alt_deg`), and `transit_utc` (hour with max altitude).
5. Discard targets where `hours_visible < min_hours`.
6. Sort remaining targets by `peak_alt_deg` descending.
7. Return first `max_results` entries.

### Error handling

- If `targets.json` is missing or malformed, return `[]` (never raise).
- If `ephem` raises for a specific target (bad RA/Dec), skip that target and continue.

---

## Component 3: GUI — Forecast Tab Detail Panel

### Where it appears

A "Recommended Targets" section is added **below** the existing left/right score+hours panel in `_forecast_detail_pane`, separated by a `ttk.Separator`. It is only shown for GO nights; for NO-GO nights the section is hidden.

### Layout

```
─────────────────────────────────────────────────────────
Recommended Targets
Name        Type               Peak Alt   Hrs Vis   Transits    Description
M13         Globular Cluster    78°        7.0h      22:14       Finest northern globular
NGC 7000    Emission Nebula     65°        6.5h      21:30       North America Nebula
...
```

Implemented as a `ttk.Treeview` with 6 columns (read-only, no selection needed). The widget is created once in `_build_forecast_tab` and shown/hidden/repopulated in `_show_forecast_detail`.

### Data flow

In `_run_forecast_load` (background thread):
- For each GO night, call `get_nightly_targets(site.lat, site.lon, window)`.
- Store result in `night["targets"]` (empty list for NO-GO nights).

In `_show_forecast_detail`:
- If `night["targets"]` is non-empty: show separator + treeview, populate rows.
- If empty (NO-GO or no visible targets): hide the section.

Transit time is displayed in local time using the site's timezone (same pattern as imaging window hours).

---

## Component 4: HTML Email

### Where it appears

After the `<pre>` text summary block for each GO site, a "Recommended Targets" HTML table is inserted. NO-GO sites get no targets section.

### Layout

Dark-themed HTML table matching the existing email style:

```html
<h4 style="...">Recommended Targets</h4>
<table style="...">
  <tr><th>Name</th><th>Type</th><th>Peak Alt</th><th>Hrs Vis</th><th>Transits (UTC)</th><th>Description</th></tr>
  <tr><td>M13</td><td>Globular Cluster</td><td>78°</td><td>7.0h</td><td>22:14</td><td>Finest northern globular</td></tr>
  ...
</table>
```

### Data flow

In `smtp_notifier.py`, for each report where `score.go` is True:
- Compute `imaging_window` using `_forecast_imaging_window(target_date, site.lat, site.lon)` (same logic as the Forecast tab).
- Call `get_nightly_targets(site.lat, site.lon, imaging_window)`.
- Render HTML table and append after the text block.
- If `get_nightly_targets` raises unexpectedly, skip silently (log warning).

Transit times displayed in UTC in the email (consistent with moon rise/set times already shown in UTC).

---

## Testing

- `test_target_recommender.py`:
  - `test_returns_empty_list_when_no_targets_visible` — imaging window entirely in daytime
  - `test_filters_below_min_alt` — target that never reaches 25°
  - `test_filters_below_min_hours` — target above 25° for only 1 hour
  - `test_sorts_by_peak_altitude` — two visible targets, higher one is first
  - `test_respects_max_results` — more than 10 qualifying targets, returns exactly 10
  - `test_returns_empty_on_missing_targets_file` — graceful failure
  - `test_transit_utc_is_hour_of_peak_altitude` — transit matches the hour with max altitude

---

## Out of Scope

- Filtering by object type (all types shown)
- Equipment FOV matching
- Mosaic planning
- Magnitude limit slider
- User-editable target list in the GUI
