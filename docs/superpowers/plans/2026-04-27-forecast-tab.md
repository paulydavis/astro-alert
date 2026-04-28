# 14-Night Forecast Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Forecast" tab showing a 14-night go/no-go outlook per site, with a click-to-expand detail panel showing score breakdown and hourly imaging-window weather.

**Architecture:** `fetch_weather_range` in `weather.py` makes a single 14-day Open-Meteo request and partitions results by date. The Forecast tab in `gui.py` fetches weather, seeing (7timer, ~7 days), and per-night moon data in a background thread, scores each night via the existing `score_night()`, then populates a `ttk.Treeview`. Clicking a row reveals a detail panel with score breakdown and the 20:00–04:00 imaging window.

**Tech Stack:** Python 3.11+, tkinter ttk.Treeview, Open-Meteo (weather), 7timer.info (seeing), ephem (moon), threading.Thread(daemon=True)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `weather.py` | Add `fetch_weather_range` (one call, partition by date) |
| Modify | `test_weather.py` | Tests for `fetch_weather_range` |
| Modify | `gui.py` | `_tab_forecast`, `_build_forecast_tab`, loading, treeview, detail panel |
| Modify | `test_gui.py` | Update tab count test (6→7), add Forecast smoke tests |

---

## Task 1: Add `fetch_weather_range` to `weather.py`

**Files:**
- Modify: `weather.py` (add after line 91, after `fetch_weather`)
- Modify: `test_weather.py` (add class at bottom)

- [ ] **Step 1: Write the failing tests**

Add at the bottom of `test_weather.py` (after line 179):

```python
# --- 14-night range ----------------------------------------------------------

class TestFetchWeatherRange:
    def test_returns_14_tuples(self):
        """fetch_weather_range returns one (date, WeatherResult) per day."""
        today = datetime.now(timezone.utc).date()
        times = [
            (datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
             + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00")
            for i in range(14 * 24)
        ]
        fake_data = {
            "hourly": {
                "time": times,
                "cloud_cover": [10] * (14 * 24),
                "precipitation": [0.0] * (14 * 24),
                "wind_speed_10m": [5.0] * (14 * 24),
                "relative_humidity_2m": [50] * (14 * 24),
                "dew_point_2m": [5.0] * (14 * 24),
                "temperature_2m": [15.0] * (14 * 24),
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        from weather import fetch_weather_range
        with patch("weather.requests.get", return_value=mock_resp):
            results = fetch_weather_range("test", 35.9, -79.0, days=14)

        assert len(results) == 14
        for i, (d, wr) in enumerate(results):
            assert d == today + timedelta(days=i)
            assert wr.ok
            assert len(wr.hours) == 24

    def test_each_result_contains_only_its_own_date_hours(self):
        """Hours in each WeatherResult all belong to that result's date."""
        today = datetime.now(timezone.utc).date()
        times = [
            (datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
             + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00")
            for i in range(14 * 24)
        ]
        fake_data = {
            "hourly": {
                "time": times,
                "cloud_cover": list(range(14 * 24)),
                "precipitation": [0.0] * (14 * 24),
                "wind_speed_10m": [5.0] * (14 * 24),
                "relative_humidity_2m": [50] * (14 * 24),
                "dew_point_2m": [5.0] * (14 * 24),
                "temperature_2m": [15.0] * (14 * 24),
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        from weather import fetch_weather_range
        with patch("weather.requests.get", return_value=mock_resp):
            results = fetch_weather_range("test", 35.9, -79.0, days=14)

        _, day0 = results[0]
        assert all(h.time.date() == today for h in day0.hours)
        _, day1 = results[1]
        assert all(h.time.date() == today + timedelta(days=1) for h in day1.hours)

    def test_api_error_returns_14_error_results(self):
        """API failure propagates an error WeatherResult for every day — never raises."""
        from weather import fetch_weather_range
        with patch("weather.requests.get",
                   side_effect=requests.ConnectionError("timeout")):
            results = fetch_weather_range("test", 35.9, -79.0, days=14)

        assert len(results) == 14
        for _, wr in results:
            assert not wr.ok
            assert wr.hours == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/pauldavis/astro_alert/.worktrees/forecast-tab
python3 -m pytest test_weather.py::TestFetchWeatherRange -v
```

Expected: FAIL — `ImportError: cannot import name 'fetch_weather_range' from 'weather'`

- [ ] **Step 3: Implement `fetch_weather_range` in `weather.py`**

Add immediately after the closing line of `fetch_weather` (after line 91):

```python
def fetch_weather_range(site_key: str, lat: float, lon: float,
                        days: int = 14) -> list[tuple[date, "WeatherResult"]]:
    """Fetch hourly weather for `days` days starting from today UTC.

    Makes one Open-Meteo API call; partitions the result by calendar date.
    Returns a list of (date, WeatherResult) tuples — always `days` entries.
    """
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days - 1)
    raw = fetch_weather(site_key, lat, lon, target_date=today, end_date=end)

    if not raw.ok:
        return [
            (today + timedelta(days=i),
             WeatherResult(site_key=site_key, fetched_at=raw.fetched_at,
                           hours=[], error=raw.error))
            for i in range(days)
        ]

    by_date: dict[date, list] = {}
    for h in raw.hours:
        d = h.time.date()
        by_date.setdefault(d, []).append(h)

    return [
        (today + timedelta(days=i),
         WeatherResult(site_key=site_key, fetched_at=raw.fetched_at,
                       hours=by_date.get(today + timedelta(days=i), [])))
        for i in range(days)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest test_weather.py -v
```

Expected: all tests PASS (including the 3 new ones in `TestFetchWeatherRange`).

- [ ] **Step 5: Commit**

```bash
git add weather.py test_weather.py
git commit -m "feat: add fetch_weather_range for 14-day forecast"
```

---

## Task 2: Add Forecast tab skeleton to `gui.py`

**Files:**
- Modify: `gui.py` — `_build_notebook` (insert `_tab_forecast`), add `_build_forecast_tab`, `_refresh_forecast_sites`, and stubs
- Modify: `test_gui.py` — rename tab-count test (6→7), add Forecast smoke tests

- [ ] **Step 1: Write the failing smoke tests in `test_gui.py`**

In `test_gui.py`, find `test_has_notebook_with_six_tabs` inside `TestAppInit` and replace it:

```python
def test_has_notebook_with_seven_tabs(self, app):
    assert hasattr(app, "_nb")
    assert app._nb.index("end") == 7

def test_forecast_tab_frame_exists(self, app):
    assert hasattr(app, "_tab_forecast")

def test_forecast_load_button_exists(self, app):
    assert hasattr(app, "_forecast_load_btn")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest test_gui.py::TestAppInit -v
```

Expected: `test_has_notebook_with_seven_tabs` FAILS (index == 6), `test_forecast_tab_frame_exists` FAILS, `test_forecast_load_button_exists` FAILS.

- [ ] **Step 3: Update `_build_notebook` in `gui.py`**

Replace the entire `_build_notebook` method (around lines 196–220):

```python
def _build_notebook(self):
    ttk.Separator(self).pack(fill="x", pady=(16, 0))
    nb = self._nb = ttk.Notebook(self)
    nb.pack(fill="both", expand=True)

    self._tab_dash     = ttk.Frame(nb)
    self._tab_sites    = ttk.Frame(nb)
    self._tab_sched    = ttk.Frame(nb)
    self._tab_forecast = ttk.Frame(nb)
    self._tab_chart    = ttk.Frame(nb)
    self._tab_scoring  = ttk.Frame(nb)
    self._tab_settings = ttk.Frame(nb)

    nb.add(self._tab_dash,     text="  Dashboard  ")
    nb.add(self._tab_sites,    text="  Sites  ")
    nb.add(self._tab_sched,    text="  Schedule  ")
    nb.add(self._tab_forecast, text="  Forecast  ")
    nb.add(self._tab_chart,    text="  Chart  ")
    nb.add(self._tab_scoring,  text="  Scoring  ")
    nb.add(self._tab_settings, text="  Settings  ")

    self._build_dashboard(self._tab_dash)
    self._build_sites_tab(self._tab_sites)
    self._build_schedule_tab(self._tab_sched)
    self._build_forecast_tab(self._tab_forecast)
    self._build_chart_tab(self._tab_chart)
    self._build_scoring_tab(self._tab_scoring)
    self._build_settings_tab(self._tab_settings)
```

- [ ] **Step 4: Add `_build_forecast_tab` and `_refresh_forecast_sites`**

Insert these methods after `_build_schedule_tab` (before `# ── Chart tab` comment, around line 569):

```python
# ── Forecast tab ─────────────────────────────────────────────────────────────

def _build_forecast_tab(self, parent):
    self._forecast_nights = []

    # ── Controls row ──────────────────────────────────────────────────────
    ctrl = ttk.Frame(parent)
    ctrl.pack(fill="x", padx=26, pady=(20, 0))

    ttk.Label(ctrl, text="Site:", style="Dim.TLabel").pack(side="left")
    self._forecast_site_var   = tk.StringVar(value="")
    self._forecast_site_combo = ttk.Combobox(ctrl, textvariable=self._forecast_site_var,
                                              state="readonly", width=24,
                                              font=(FONT_PROP, 12))
    self._forecast_site_combo.pack(side="left", padx=(8, 0))

    self._forecast_load_btn = ttk.Button(ctrl, text="Load Forecast",
                                          style="Accent.TButton",
                                          command=self._start_forecast_load)
    self._forecast_load_btn.pack(side="left", padx=(16, 0))

    self._forecast_error_var = tk.StringVar(value="")
    ttk.Label(ctrl, textvariable=self._forecast_error_var,
              style="Dim.TLabel", foreground=WARN_CLR).pack(side="left", padx=(16, 0))

    ttk.Separator(parent).pack(fill="x", pady=(14, 0))

    # ── Treeview ──────────────────────────────────────────────────────────
    tree_frame = ttk.Frame(parent)
    tree_frame.pack(fill="x", padx=26, pady=(12, 0))

    cols = ("date", "verdict", "score", "clouds", "moon")
    self._forecast_tree = ttk.Treeview(tree_frame, columns=cols,
                                        show="headings", height=14,
                                        selectmode="browse")

    self._forecast_tree.heading("date",    text="Date")
    self._forecast_tree.heading("verdict", text="Verdict")
    self._forecast_tree.heading("score",   text="Score")
    self._forecast_tree.heading("clouds",  text="Clouds")
    self._forecast_tree.heading("moon",    text="Moon")

    self._forecast_tree.column("date",    width=130, anchor="w")
    self._forecast_tree.column("verdict", width=80,  anchor="center")
    self._forecast_tree.column("score",   width=80,  anchor="center")
    self._forecast_tree.column("clouds",  width=80,  anchor="center")
    self._forecast_tree.column("moon",    width=80,  anchor="center")

    self._forecast_tree.tag_configure("go",   foreground=GO_CLR)
    self._forecast_tree.tag_configure("nogo", foreground=NOGO_CLR)
    self._forecast_tree.tag_configure("warn", foreground=WARN_CLR)

    vsb = ttk.Scrollbar(tree_frame, command=self._forecast_tree.yview)
    self._forecast_tree.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    self._forecast_tree.pack(side="left", fill="x", expand=True)

    self._forecast_tree.bind("<<TreeviewSelect>>", self._on_forecast_select)

    # ── Detail panel (hidden until first row selection) ───────────────────
    self._forecast_detail_sep  = ttk.Separator(parent)
    self._forecast_detail_pane = ttk.Frame(parent, style="Card.TFrame")

    detail_inner = ttk.Frame(self._forecast_detail_pane, style="Card.TFrame")
    detail_inner.pack(fill="both", expand=True, padx=26, pady=12)

    left = ttk.Frame(detail_inner, style="Card.TFrame")
    left.pack(side="left", fill="both", expand=True)

    self._detail_score_lbl   = ttk.Label(left, text="", style="Card.TLabel",
                                          font=(FONT_PROP, 22, "bold"))
    self._detail_score_lbl.pack(anchor="w", pady=(8, 4))
    self._detail_weather_lbl = ttk.Label(left, text="", style="CardDim.TLabel")
    self._detail_weather_lbl.pack(anchor="w")
    self._detail_seeing_lbl  = ttk.Label(left, text="", style="CardDim.TLabel")
    self._detail_seeing_lbl.pack(anchor="w")
    self._detail_moon_lbl    = ttk.Label(left, text="", style="CardDim.TLabel")
    self._detail_moon_lbl.pack(anchor="w")
    self._detail_warn_lbl    = ttk.Label(left, text="", style="CardDim.TLabel",
                                          foreground=WARN_CLR, wraplength=350)
    self._detail_warn_lbl.pack(anchor="w", pady=(8, 0))

    ttk.Separator(detail_inner, orient="vertical").pack(
        side="left", fill="y", padx=18, pady=8)

    right = ttk.Frame(detail_inner, style="Card.TFrame")
    right.pack(side="left", fill="both", expand=True)

    ttk.Label(right, text="Imaging Window  (20:00–04:00 UTC)",
              style="CardDim.TLabel").pack(anchor="w", pady=(8, 4))
    self._detail_hours_txt = tk.Text(
        right, bg=CARD, fg=TEXT, font=(FONT_MONO, 11),
        relief="flat", bd=0, state="disabled", height=10, width=42,
        padx=4, pady=4,
    )
    self._detail_hours_txt.pack(anchor="w")

    self.after(150, self._refresh_forecast_sites)


def _refresh_forecast_sites(self):
    if not hasattr(self, "_forecast_site_combo"):
        return
    try:
        from site_manager import list_sites
        entries = list_sites()
    except FileNotFoundError:
        entries = []
    options = [f"{k}: {s.name}" for k, s, _ in entries]
    self._forecast_site_combo.configure(values=options)
    if options and not self._forecast_site_var.get():
        self._forecast_site_var.set(options[0])
```

- [ ] **Step 5: Add stub methods so the app does not crash**

Add immediately after `_refresh_forecast_sites`:

```python
def _start_forecast_load(self):
    pass  # implemented in Task 3

def _on_forecast_select(self, _event):
    pass  # implemented in Task 3
```

- [ ] **Step 6: Run smoke tests to verify they pass**

```bash
python3 -m pytest test_gui.py::TestAppInit -v
```

Expected: `test_has_notebook_with_seven_tabs` PASS, `test_forecast_tab_frame_exists` PASS, `test_forecast_load_button_exists` PASS.

- [ ] **Step 7: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: add Forecast tab skeleton with treeview and detail panel frame"
```

---

## Task 3: Implement data loading, treeview population, and detail panel

**Files:**
- Modify: `gui.py` — replace stubs for `_start_forecast_load` and `_on_forecast_select`; add `_run_forecast_load`, `_forecast_loaded`, `_forecast_load_failed`, `_show_forecast_detail`

- [ ] **Step 1: Replace `_start_forecast_load` stub**

Replace the stub (the `pass` body) with:

```python
def _start_forecast_load(self):
    site_val = self._forecast_site_var.get()
    if not site_val:
        return
    self._forecast_load_btn.configure(state="disabled", text="Loading…")
    self._forecast_error_var.set("")
    self._forecast_tree.delete(*self._forecast_tree.get_children())
    self._forecast_nights = []
    key = site_val.split(":")[0].strip()
    threading.Thread(target=self._run_forecast_load, args=(key,), daemon=True).start()
```

- [ ] **Step 2: Add `_run_forecast_load` after `_start_forecast_load`**

```python
def _run_forecast_load(self, site_key: str):
    from datetime import datetime, timedelta, timezone
    from site_manager import get_active_site
    from weather import fetch_weather_range
    from seeing import fetch_seeing, SeeingResult
    from moon import get_moon_info
    from scorer import score_night

    def _imaging_window(target_date):
        ev = {
            datetime(target_date.year, target_date.month, target_date.day,
                     h, tzinfo=timezone.utc)
            for h in range(20, 24)
        }
        nd = target_date + timedelta(days=1)
        ea = {
            datetime(nd.year, nd.month, nd.day, h, tzinfo=timezone.utc)
            for h in range(0, 5)
        }
        return ev | ea

    try:
        site         = get_active_site(override=site_key)
        weather_days = fetch_weather_range(site.key, site.lat, site.lon, days=14)
        seeing_all   = fetch_seeing(site.key, site.lat, site.lon)

        # Build lookup of seeing hours by rounded UTC datetime
        seeing_by_time: dict = {}
        if seeing_all.ok:
            for sh in seeing_all.hours:
                t = sh.time.replace(minute=0, second=0, microsecond=0)
                seeing_by_time[t] = sh

        nights = []
        for target_date, weather in weather_days:
            moon   = get_moon_info(site.lat, site.lon, target_date)
            window = _imaging_window(target_date)

            night_seeing_hours = [seeing_by_time[t] for t in window
                                   if t in seeing_by_time]

            if night_seeing_hours:
                night_seeing = SeeingResult(
                    site_key=site.key,
                    fetched_at=seeing_all.fetched_at,
                    hours=night_seeing_hours,
                )
                seeing_available = True
            elif not seeing_all.ok:
                night_seeing = SeeingResult(
                    site_key=site.key,
                    fetched_at=seeing_all.fetched_at,
                    hours=[], error=seeing_all.error,
                )
                seeing_available = False
            else:
                # Seeing fetched OK but no data for this night (beyond ~7 days)
                night_seeing = SeeingResult(
                    site_key=site.key,
                    fetched_at=seeing_all.fetched_at,
                    hours=[], error="Beyond 7-day forecast range",
                )
                seeing_available = False

            score = score_night(weather, night_seeing, moon, site.bortle, target_date)
            nights.append({
                "date":             target_date,
                "score":            score,
                "moon":             moon,
                "weather":          weather,
                "seeing_available": seeing_available,
            })

        self.after(0, self._forecast_loaded, nights)
    except Exception as e:
        self.after(0, self._forecast_load_failed, str(e))
```

- [ ] **Step 3: Add `_forecast_loaded` and `_forecast_load_failed` after `_run_forecast_load`**

```python
def _forecast_loaded(self, nights: list):
    self._forecast_nights = nights
    self._forecast_load_btn.configure(state="normal", text="Load Forecast")
    self._forecast_error_var.set("")
    self._forecast_tree.delete(*self._forecast_tree.get_children())

    for night in nights:
        target_date = night["date"]
        score       = night["score"]
        moon        = night["moon"]

        date_str    = target_date.strftime("%a %b %-d")
        verdict_str = "GO" if score.go else "no-go"
        score_str   = f"{score.total}/100"
        cloud_str   = f"{score.avg_cloud_pct}%" if score.avg_cloud_pct >= 0 else "—"
        moon_str    = f"{moon.phase_pct:.0f}%"

        tag = "go" if score.go else "nogo"
        self._forecast_tree.insert("", "end",
            values=(date_str, verdict_str, score_str, cloud_str, moon_str),
            tags=(tag,))

    self._set_status("Forecast loaded.")


def _forecast_load_failed(self, msg: str):
    self._forecast_load_btn.configure(state="normal", text="Load Forecast")
    self._forecast_error_var.set(f"Error: {msg}")
    self._set_status("Forecast load failed.")
```

- [ ] **Step 4: Replace `_on_forecast_select` stub and add `_show_forecast_detail`**

Replace stub `_on_forecast_select` with:

```python
def _on_forecast_select(self, _event):
    sel = self._forecast_tree.selection()
    if not sel:
        return
    idx = self._forecast_tree.index(sel[0])
    if idx >= len(self._forecast_nights):
        return
    if not self._forecast_detail_pane.winfo_ismapped():
        self._forecast_detail_sep.pack(fill="x", pady=(12, 0))
        self._forecast_detail_pane.pack(
            fill="both", expand=True, padx=26, pady=(8, 16))
    self._show_forecast_detail(self._forecast_nights[idx])


def _show_forecast_detail(self, night: dict):
    from datetime import datetime, timedelta, timezone

    score = night["score"]
    moon  = night["moon"]

    go_color = GO_CLR if score.go else NOGO_CLR
    verdict  = "GO" if score.go else "NO-GO"
    self._detail_score_lbl.configure(
        text=f"{verdict}  {score.total}/100", foreground=go_color)
    self._detail_weather_lbl.configure(
        text=f"Weather:  {score.weather_score}/100")

    if night["seeing_available"]:
        self._detail_seeing_lbl.configure(
            text=f"Seeing:   {score.seeing_score}/100")
    else:
        self._detail_seeing_lbl.configure(text="Seeing:   N/A")

    self._detail_moon_lbl.configure(
        text=f"Moon:     {score.moon_score}/100  "
             f"({moon.phase_pct:.0f}% illuminated)")

    warnings = [w for w in score.warnings
                if "Seeing data" not in w and "Beyond 7-day" not in w]
    self._detail_warn_lbl.configure(
        text="\n".join(warnings) if warnings else "")

    # ── Hourly imaging window ──────────────────────────────────────────────
    weather     = night["weather"]
    target_date = night["date"]

    self._detail_hours_txt.configure(state="normal")
    self._detail_hours_txt.delete("1.0", "end")

    if not weather.ok or not weather.hours:
        self._detail_hours_txt.insert("end", "Weather data unavailable.")
    else:
        evening = {
            datetime(target_date.year, target_date.month, target_date.day,
                     h, tzinfo=timezone.utc)
            for h in range(20, 24)
        }
        next_day = target_date + timedelta(days=1)
        early = {
            datetime(next_day.year, next_day.month, next_day.day,
                     h, tzinfo=timezone.utc)
            for h in range(0, 5)
        }
        window = evening | early

        night_rows = sorted(
            [h for h in weather.hours if h.time in window],
            key=lambda h: h.time,
        )

        self._detail_hours_txt.insert(
            "end", f"{'Hour':>5}  {'Clouds':>6}  {'Wind':>7}  {'Humidity':>8}\n")
        self._detail_hours_txt.insert("end", "─" * 36 + "\n")

        for h in night_rows:
            self._detail_hours_txt.insert(
                "end",
                f"{h.time.strftime('%H:00'):>5}  "
                f"{h.cloud_cover_pct:>5}%  "
                f"{h.wind_speed_kmh:>5.0f}km/h  "
                f"{h.humidity_pct:>6}%\n",
            )

        if not night_rows:
            self._detail_hours_txt.insert("end", "No hours in imaging window.")

    self._detail_hours_txt.configure(state="disabled")
```

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest test_weather.py test_gui.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Launch the app and test the Forecast tab manually**

```bash
python3 gui.py
```

Verify:
1. "Forecast" tab appears between "Schedule" and "Chart"
2. Site combobox is populated; selecting a site and clicking "Load Forecast" loads 14 rows
3. Each row shows date, GO/no-go verdict (colored), score, avg cloud %, moon %
4. Clicking any row reveals the detail panel below the treeview
5. Detail panel shows total score (large, colored), weather/seeing/moon sub-scores, warnings
6. Right side shows the 20:00–04:00 hourly imaging window table
7. For nights beyond ~7 days, "Seeing: N/A" appears in the detail panel

- [ ] **Step 7: Commit**

```bash
git add gui.py
git commit -m "feat: implement Forecast tab with 14-night treeview and detail panel"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `fetch_weather_range` — one API call, 14 days, partitioned by date | Task 1 |
| 7timer seeing ~7 days; N/A beyond range; re-normalized score | Task 3, `_run_forecast_load` seeing filter; `score_night` handles missing seeing (0.5 neutral) |
| `get_moon_info` for all 14 nights | Task 3, `_run_forecast_load` per-night loop |
| `score_night` called per night | Task 3, `_run_forecast_load` |
| Background thread, daemon=True | Task 3, `_start_forecast_load` |
| Per-site cache cleared on site change | Task 3, `_start_forecast_load` resets `_forecast_nights` |
| "  Forecast  " tab after Schedule, before Chart | Task 2, `_build_notebook` |
| Site selector combobox, single-site only | Task 2, `_build_forecast_tab` |
| "Load Forecast" button, disabled during fetch, shows "Loading…" | Tasks 2+3 |
| 14-night Treeview — Date, Verdict, Score, Clouds, Moon columns | Task 2, `_build_forecast_tab` |
| `go` (GO_CLR) / `nogo` (NOGO_CLR) row tags | Tasks 2+3 |
| Fetch-error rows show "—" for numeric fields | Task 3, `_forecast_loaded` (`avg_cloud_pct >= 0` guard) |
| Detail panel hidden until first row selection | Tasks 2+3, `_on_forecast_select` |
| Detail panel: total score (large, colored) | Task 3, `_show_forecast_detail` |
| Detail panel: weather/seeing/moon sub-scores | Task 3, `_show_forecast_detail` |
| Detail panel: warnings list | Task 3, `_show_forecast_detail` |
| Detail panel: seeing "N/A" for nights beyond ~7 days | Task 3, `_show_forecast_detail` |
| Detail panel: hourly imaging window 20:00–04:00 | Task 3, `_show_forecast_detail` |
| `test_fetch_weather_range` in `test_weather.py` | Task 1 |
| Forecast tab smoke tests in `test_gui.py` | Task 2 |
| No sites configured → combobox empty | Task 2, `_refresh_forecast_sites` |

All spec requirements covered. No placeholders. Type and method names consistent across all tasks.
