# Map Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed an interactive OpenStreetMap in the Sites tab as a horizontal split view — site list on the left, map with pins on the right.

**Architecture:** The Sites tab `_build_sites_tab` method is refactored to use a horizontal `ttk.PanedWindow`; left pane holds the existing `_tree` + scrollbar; right pane holds a `tkintermapview.TkinterMapView`. `_refresh_sites` is extended to sync markers after every site list change. Map click opens the Add Site dialog with lat/lon pre-filled.

**Tech Stack:** Python 3.11+, Tkinter/ttk, `tkintermapview` (OSM tiles, no API key)

---

## File Map

| File | Change |
|---|---|
| `requirements.txt` | Add `tkintermapview>=2.20` |
| `gui.py` | Refactor `_build_sites_tab`, extend `_refresh_sites`, add `_sync_map_markers` and `_on_map_click` helpers |
| `test_gui.py` | Add `TestMapWidget` class with 5 tests |

---

### Task 1: Add dependency and import guard

**Files:**
- Modify: `requirements.txt`
- Modify: `gui.py` (top-level import block, lines ~1–30)

- [ ] **Step 1: Add `tkintermapview` to requirements**

Open `requirements.txt`. Add one line:

```
tkintermapview>=2.20
```

Full file after edit:
```
requests>=2.28
ephem>=4.1
python-dotenv>=1.0
tkintermapview>=2.20
```

- [ ] **Step 2: Install the package**

```bash
pip install tkintermapview>=2.20
```

Expected: Successfully installed tkintermapview-...

- [ ] **Step 3: Add import guard at the top of `gui.py`**

Find the block of imports near the top of `gui.py` (around line 1–25, after the standard library imports). Add these lines after the existing imports:

```python
try:
    import tkintermapview
    _MAP_AVAILABLE = True
except ImportError:
    _MAP_AVAILABLE = False
```

- [ ] **Step 4: Run existing tests to confirm nothing broke**

```bash
cd /Users/pauldavis/astro_alert && pytest test_gui.py -v
```

Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt gui.py
git commit -m "feat: add tkintermapview dependency and import guard"
```

---

### Task 2: Write failing tests for the map widget

**Files:**
- Test: `test_gui.py`

- [ ] **Step 1: Add `TestMapWidget` class to `test_gui.py`**

Append the following class at the end of `test_gui.py`:

```python
# ── Map widget ────────────────────────────────────────────────────────────────

class TestMapWidget:
    def test_map_widget_or_fallback_label_exists(self, app):
        """Sites tab must have either a map widget or a fallback label."""
        assert hasattr(app, "_map_widget") or hasattr(app, "_map_fallback_label")

    def test_sites_paned_window_is_horizontal(self, app):
        """Sites tab must use a horizontal PanedWindow."""
        assert hasattr(app, "_sites_paned")
        assert str(app._sites_paned.cget("orient")) == "horizontal"

    def test_tree_still_exists_after_map_added(self, app):
        """Existing site list treeview must still be present."""
        assert hasattr(app, "_tree")
        app._refresh_sites()
        keys = set(app._tree.get_children())
        assert "home" in keys

    def test_sync_map_markers_does_not_raise_without_map(self, app):
        """_sync_map_markers must be safe to call even when map is unavailable."""
        if hasattr(app, "_map_widget"):
            app._map_widget = None
        app._sync_map_markers()  # must not raise

    def test_refresh_sites_calls_sync_map_markers(self, app, monkeypatch):
        """_refresh_sites must call _sync_map_markers to keep pins in sync."""
        called = []
        monkeypatch.setattr(app, "_sync_map_markers", lambda: called.append(1))
        app._refresh_sites()
        assert called, "_sync_map_markers was not called by _refresh_sites"
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd /Users/pauldavis/astro_alert && pytest test_gui.py::TestMapWidget -v
```

Expected: All 5 tests FAIL (attributes don't exist yet).

- [ ] **Step 3: Commit the failing tests**

```bash
git add test_gui.py
git commit -m "test: add failing tests for map widget in Sites tab"
```

---

### Task 3: Refactor `_build_sites_tab` with PanedWindow + map

**Files:**
- Modify: `gui.py:384–416` (`_build_sites_tab` method)

- [ ] **Step 1: Replace `_build_sites_tab` with the new implementation**

Find the current `_build_sites_tab` method (lines 384–416). Replace the entire method body with:

```python
    def _build_sites_tab(self, parent):
        self._sites_paned = ttk.PanedWindow(parent, orient="horizontal")
        self._sites_paned.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Left pane: site list + buttons ──────────────────────────────────
        left = ttk.Frame(self._sites_paned)
        self._sites_paned.add(left, weight=1)

        cols = ("key", "name", "bortle", "drive", "timezone", "active")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                   selectmode="browse")

        for cid, heading, width, anchor in [
            ("key",      "Key",       110, "w"),
            ("name",     "Name",      160, "w"),
            ("bortle",   "Bortle",     60, "center"),
            ("drive",    "Drive",      70, "center"),
            ("timezone", "Timezone",  150, "w"),
            ("active",   "Active",     50, "center"),
        ]:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=width, minwidth=40, anchor=anchor)

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(18, 0), pady=16)
        vsb.pack(side="left", fill="y", pady=16)

        btns = ttk.Frame(left)
        btns.pack(side="right", fill="y", padx=16, pady=16)

        ttk.Button(btns, text="Add Site",
                   command=self._add_site_dialog).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Edit Site",
                   command=self._edit_site_dialog).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Set Active", style="Accent.TButton",
                   command=self._set_active_site).pack(fill="x", pady=(0, 8))
        ttk.Separator(btns).pack(fill="x", pady=8)
        ttk.Button(btns, text="Delete Site", style="Danger.TButton",
                   command=self._delete_site).pack(fill="x")

        # ── Right pane: map ──────────────────────────────────────────────────
        right = ttk.Frame(self._sites_paned)
        self._sites_paned.add(right, weight=2)

        if _MAP_AVAILABLE:
            self._map_widget = tkintermapview.TkinterMapView(
                right, corner_radius=0)
            self._map_widget.pack(fill="both", expand=True)
            self._map_widget.add_left_click_map_command(self._on_map_click)
        else:
            self._map_widget = None
            self._map_fallback_label = ttk.Label(
                right,
                text="Map requires tkintermapview — run:  pip install tkintermapview",
                style="Dim.TLabel",
            )
            self._map_fallback_label.pack(expand=True)
```

- [ ] **Step 2: Run the tests**

```bash
cd /Users/pauldavis/astro_alert && pytest test_gui.py -v
```

Expected: `test_map_widget_or_fallback_label_exists`, `test_sites_paned_window_is_horizontal`, and `test_tree_still_exists_after_map_added` now PASS. The two sync tests still FAIL.

- [ ] **Step 3: Commit**

```bash
git add gui.py
git commit -m "feat: refactor Sites tab to horizontal PanedWindow with map pane"
```

---

### Task 4: Add `_sync_map_markers` and wire into `_refresh_sites`

**Files:**
- Modify: `gui.py` (`_refresh_sites` and new `_sync_map_markers` method)

- [ ] **Step 1: Add `_sync_map_markers` method**

Find the end of `_refresh_sites` (around line 441) and add the new method immediately after it:

```python
    def _sync_map_markers(self):
        """Clear and redraw all site pins on the map."""
        if not getattr(self, "_map_widget", None):
            return
        self._map_widget.delete_all_marker()
        try:
            entries = list_sites()
        except FileNotFoundError:
            return
        if not entries:
            self._map_widget.set_position(39.0, -95.0, zoom=4)
            return
        lats = [s.lat for _, s, _ in entries]
        lons = [s.lon for _, s, _ in entries]
        for key, site, _ in entries:
            label = f"{site.name}  (Bortle {site.bortle})"
            self._map_widget.set_marker(
                site.lat, site.lon, text=label,
                command=lambda m, k=key: self._on_map_marker_click(k),
            )
        if len(entries) == 1:
            self._map_widget.set_position(lats[0], lons[0], zoom=10)
        else:
            padding = 0.5
            self._map_widget.fit_bounding_box(
                (max(lats) + padding, min(lons) - padding),
                (min(lats) - padding, max(lons) + padding),
            )
```

- [ ] **Step 2: Add `_on_map_marker_click` method** (immediately after `_sync_map_markers`):

```python
    def _on_map_marker_click(self, site_key: str):
        """Switch to Forecast tab and select the given site."""
        self._nb.select(self._tab_forecast)
        target_option = next(
            (opt for opt in self._site_combo.cget("values")
             if opt.startswith(f"{site_key}:")),
            None,
        )
        if target_option:
            self._site_var.set(target_option)
```

- [ ] **Step 3: Add `_on_map_click` method** (immediately after `_on_map_marker_click`):

```python
    def _on_map_click(self, coords):
        """Open Add Site dialog with lat/lon pre-filled from map click."""
        lat, lon = coords
        dlg = SiteDialog(self, title="Add Site",
                         prefill_lat=lat, prefill_lon=lon)
        self.wait_window(dlg)
        if dlg.result:
            try:
                add_site(**dlg.result)
                self._refresh_sites()
                self._set_status(f"Site '{dlg.result['key']}' added.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)
```

- [ ] **Step 4: Wire `_sync_map_markers` into `_refresh_sites`**

Find `_refresh_sites` (around line 418). At the very end of the method (after the `_site_combo` block), add one line:

```python
        self._sync_map_markers()
```

So the end of `_refresh_sites` looks like:

```python
        if hasattr(self, "_site_combo"):
            try:
                entries = list_sites()
            except FileNotFoundError:
                entries = []
            options = ["All sites"] + [f"{k}: {s.name}" for k, s, _ in entries]
            self._site_combo.configure(values=options)
            if self._site_var.get() not in options:
                self._site_var.set("All sites")

        self._sync_map_markers()
```

- [ ] **Step 5: Run the tests**

```bash
cd /Users/pauldavis/astro_alert && pytest test_gui.py -v
```

Expected: All 5 `TestMapWidget` tests PASS, and all previously passing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add gui.py
git commit -m "feat: add _sync_map_markers, _on_map_marker_click, _on_map_click"
```

---

### Task 5: Support `prefill_lat` / `prefill_lon` in `SiteDialog`

**Files:**
- Modify: `gui.py:1822–1834` (`SiteDialog.__init__`)

The `_on_map_click` handler passes `prefill_lat` and `prefill_lon` to `SiteDialog`, but the current constructor doesn't accept them. This task adds support.

- [ ] **Step 1: Update `SiteDialog.__init__` signature and defaults**

Find `SiteDialog.__init__` (line 1822). Replace:

```python
    def __init__(self, parent, title="Site", site=None, key=None):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.geometry("520x660")
        self.minsize(520, 480)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.result       = None
        self._editing_key = key
        self._geo_results: list[dict] = []
        self._build(site, key)
```

With:

```python
    def __init__(self, parent, title="Site", site=None, key=None,
                 prefill_lat=None, prefill_lon=None):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.geometry("520x660")
        self.minsize(520, 480)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.result         = None
        self._editing_key   = key
        self._prefill_lat   = prefill_lat
        self._prefill_lon   = prefill_lon
        self._geo_results: list[dict] = []
        self._build(site, key)
```

- [ ] **Step 2: Apply prefill values in `_build`**

Find the `defaults` dict inside `SiteDialog._build` (around line 1903):

```python
        defaults = {
            "key":         key or "",
            "name":        getattr(site, "name",        "") or "",
            "lat":         str(getattr(site, "lat",     "")) if site else "",
            "lon":         str(getattr(site, "lon",     "")) if site else "",
```

Replace those two lat/lon lines with:

```python
            "lat":         str(getattr(site, "lat", "")) if site else (
                               f"{self._prefill_lat:.6f}" if self._prefill_lat is not None else ""),
            "lon":         str(getattr(site, "lon", "")) if site else (
                               f"{self._prefill_lon:.6f}" if self._prefill_lon is not None else ""),
```

- [ ] **Step 3: Run all tests**

```bash
cd /Users/pauldavis/astro_alert && pytest test_gui.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add gui.py
git commit -m "feat: SiteDialog accepts prefill_lat/prefill_lon from map click"
```

---

### Task 6: Manual smoke test and README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Launch the app**

```bash
cd /Users/pauldavis/astro_alert && python gui.py
```

Verify:
1. Sites tab shows map on the right with one pin per site
2. Dragging the sash resizes list and map
3. Clicking a pin shows a popup with site name and Bortle class
4. Clicking the map background opens Add Site with lat/lon pre-filled
5. Adding a site causes the map to show a new pin immediately

- [ ] **Step 2: Update README**

Find the Sites tab section in `README.md`. Update it to mention:
- The map panel on the right of the Sites tab
- Clicking a pin to jump to Forecast for that site
- Clicking the map to open Add Site with coordinates pre-filled

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/pauldavis/astro_alert && pytest -v
```

Expected: All tests PASS.

- [ ] **Step 4: Final commit**

```bash
git add README.md
git commit -m "docs: update README for Sites tab map feature"
```
