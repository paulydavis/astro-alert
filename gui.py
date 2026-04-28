#!/usr/bin/env python3
"""Astro Alert — GUI configuration and control panel."""

import io
import platform
import re
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import scheduler_setup
import site_manager as sm
from astro_alert import build_parser, cmd_run
from site_manager import add_site, delete_site, list_sites, set_active_site

try:
    import tkintermapview
    _MAP_AVAILABLE = True
except ImportError:
    _MAP_AVAILABLE = False

# ── Platform fonts ─────────────────────────────────────────────────────────────
_OS        = platform.system()
FONT_PROP  = {"Darwin": "Helvetica", "Windows": "Segoe UI"}.get(_OS, "DejaVu Sans")
FONT_MONO  = {"Darwin": "Menlo",     "Windows": "Consolas"}.get(_OS, "DejaVu Sans Mono")

# ── Colour palette (GitHub-dark inspired, astronomy accents) ──────────────────
BG        = "#0d1117"
CARD      = "#161b22"
BORDER    = "#30363d"
TEXT      = "#c9d1d9"
TEXT_DIM  = "#8b949e"
ACCENT    = "#58a6ff"
GO_CLR    = "#3fb950"
NOGO_CLR  = "#f85149"
WARN_CLR  = "#e3b341"
BTN_BG    = "#21262d"
BTN_ACT   = "#30363d"
STATUS_BG = "#010409"


# ── Routing helpers ────────────────────────────────────────────────────────────

def _get_home_location():
    """Return (lat, lon) from the saved home location, or None if not set."""
    from data_dir import ENV_FILE
    from dotenv import dotenv_values
    vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    try:
        return float(vals["HOME_LAT"]), float(vals["HOME_LON"])
    except (KeyError, ValueError):
        return None


def _osrm_drive_minutes(home_lat: float, home_lon: float,
                         site_lat: float, site_lon: float) -> int:
    """Return driving minutes between two points via the public OSRM API."""
    import requests
    url = (f"https://router.project-osrm.org/route/v1/driving/"
           f"{home_lon},{home_lat};{site_lon},{site_lat}?overview=false")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    seconds = resp.json()["routes"][0]["duration"]
    return round(seconds / 60)


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


def _forecast_imaging_window(target_date, lat=None, lon=None):
    """Return the set of UTC datetimes covering sunset→sunrise for target_date's imaging night."""
    if lat is not None and lon is not None:
        from moon import compute_imaging_window
        return compute_imaging_window(lat, lon, target_date)
    from datetime import datetime, timedelta, timezone
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


# ─────────────────────────────────────────────────────────────────────────────
# Main application window
# ─────────────────────────────────────────────────────────────────────────────

class AstroAlertApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Astro Alert")
        self.configure(bg=BG)
        self.geometry("980x680")
        self.minsize(800, 540)

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        self.after(100, self._refresh_sites)
        self.after(200, self._refresh_cred_banner)
        self.after(400, self._check_first_run)

    # ── Styles ─────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".",
                     background=BG, foreground=TEXT,
                     font=(FONT_PROP, 12), borderwidth=0, relief="flat")

        s.configure("TNotebook", background=BG, tabmargins=[0, 0, 0, 0])
        s.configure("TNotebook.Tab",
                     background=BTN_BG, foreground=TEXT_DIM,
                     padding=[20, 10], font=(FONT_PROP, 12))
        s.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", TEXT)])

        s.configure("TFrame",      background=BG)
        s.configure("Card.TFrame", background=CARD)

        s.configure("TLabel",         background=BG,   foreground=TEXT,     font=(FONT_PROP, 12))
        s.configure("H1.TLabel",      background=BG,   foreground=TEXT,     font=(FONT_PROP, 22, "bold"))
        s.configure("Sub.TLabel",     background=BG,   foreground=TEXT_DIM, font=(FONT_PROP, 12))
        s.configure("Dim.TLabel",     background=BG,   foreground=TEXT_DIM, font=(FONT_PROP, 11))
        s.configure("Card.TLabel",    background=CARD, foreground=TEXT,     font=(FONT_PROP, 12))
        s.configure("CardDim.TLabel", background=CARD, foreground=TEXT_DIM, font=(FONT_PROP, 11))
        s.configure("Status.TLabel",  background=STATUS_BG, foreground=TEXT_DIM, font=(FONT_PROP, 11))

        s.configure("TButton",
                     background=BTN_BG, foreground=TEXT,
                     font=(FONT_PROP, 12), padding=[13, 7], relief="flat")
        s.map("TButton",
              background=[("active", BTN_ACT), ("pressed", BORDER)],
              relief=[("pressed", "flat")])

        s.configure("Accent.TButton",
                     background=ACCENT, foreground="#000000",
                     font=(FONT_PROP, 12, "bold"), padding=[15, 8])
        s.map("Accent.TButton",
              background=[("active", "#79c0ff"), ("pressed", "#388bfd")])

        s.configure("Go.TButton",
                     background=GO_CLR, foreground="#000000",
                     font=(FONT_PROP, 12, "bold"), padding=[15, 8])
        s.map("Go.TButton",
              background=[("active", "#56d364"), ("pressed", "#2ea043")])

        s.configure("Danger.TButton",
                     background="#da3633", foreground="#ffffff",
                     font=(FONT_PROP, 12), padding=[13, 7])
        s.map("Danger.TButton",
              background=[("active", "#f85149"), ("pressed", "#b22222")])

        s.configure("Treeview",
                     background=CARD, foreground=TEXT,
                     fieldbackground=CARD, rowheight=34, font=(FONT_PROP, 12))
        s.configure("Treeview.Heading",
                     background=BTN_BG, foreground=TEXT_DIM,
                     font=(FONT_PROP, 11, "bold"), relief="flat", padding=[8, 7])
        s.map("Treeview",
              background=[("selected", "#1f3f5e")],
              foreground=[("selected", TEXT)])

        s.configure("TEntry",
                     fieldbackground=BTN_BG, foreground=TEXT,
                     insertcolor=TEXT, relief="flat", padding=[7, 5])
        s.configure("TCombobox",
                     fieldbackground=BTN_BG, foreground=TEXT,
                     background=BTN_BG, arrowcolor=TEXT_DIM, relief="flat")
        s.map("TCombobox",
              fieldbackground=[("readonly", BTN_BG)],
              foreground=[("readonly", TEXT)])

        s.configure("TRadiobutton", background=BG, foreground=TEXT, font=(FONT_PROP, 12))
        s.configure("TCheckbutton", background=BG, foreground=TEXT, font=(FONT_PROP, 12))

        s.configure("TSeparator", background=BORDER)
        s.configure("TScrollbar",
                     background=BTN_BG, troughcolor=CARD,
                     arrowcolor=TEXT_DIM, borderwidth=0)

    # ── Header ──────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=26, pady=(20, 0))
        ttk.Label(hdr, text="🔭  Astro Alert", style="H1.TLabel").pack(side="left")
        ttk.Label(hdr, text="Astrophotography go / no-go system",
                  style="Sub.TLabel").pack(side="left", padx=(16, 0), pady=(9, 0))

    # ── Notebook ────────────────────────────────────────────────────────────────

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

    # ── Dashboard ───────────────────────────────────────────────────────────────

    def _build_dashboard(self, parent):
        # Credential warning banner (hidden until _refresh_cred_banner decides)
        self._cred_warn = tk.Frame(parent, bg=WARN_CLR)
        tk.Label(self._cred_warn, text="⚠  Email credentials not configured — alerts won't send.",
                 bg=WARN_CLR, fg="#000000", font=(FONT_PROP, 12)).pack(side="left",
                 padx=16, pady=8)
        ttk.Button(self._cred_warn, text="Set up →",
                   command=lambda: self._nb.select(self._tab_settings)).pack(
            side="left", padx=(0, 12))

        # Controls row
        ctrl = self._ctrl_frame = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=26, pady=(20, 0))

        self._night_var = tk.StringVar(value="tonight")
        for label, val in (("Tonight", "tonight"), ("Tomorrow night", "tomorrow")):
            ttk.Radiobutton(ctrl, text=label, variable=self._night_var,
                             value=val).pack(side="left", padx=(0, 8))

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=16, pady=4)

        ttk.Label(ctrl, text="Site:", style="Dim.TLabel").pack(side="left")
        self._site_var   = tk.StringVar(value="All sites")
        self._site_combo = ttk.Combobox(ctrl, textvariable=self._site_var,
                                         state="readonly", width=24,
                                         font=(FONT_PROP, 12))
        self._site_combo.pack(side="left", padx=(8, 0))

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=16, pady=4)

        self._dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Dry run  (no email)",
                         variable=self._dry_run_var).pack(side="left")

        self._run_btn = ttk.Button(ctrl, text="▶  Run Forecast",
                                    style="Go.TButton",
                                    command=self._start_forecast)
        self._run_btn.pack(side="right")

        # Output panel
        panel = ttk.Frame(parent, style="Card.TFrame")
        panel.pack(fill="both", expand=True, padx=26, pady=18)

        self._output = tk.Text(
            panel,
            bg=CARD, fg=TEXT, insertbackground=TEXT,
            font=(FONT_MONO, 12), relief="flat", bd=0,
            wrap="word", state="disabled",
            padx=18, pady=16,
            selectbackground="#1f3f5e", selectforeground=TEXT,
            spacing3=2,
        )
        vsb = ttk.Scrollbar(panel, command=self._output.yview)
        self._output.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._output.pack(side="left", fill="both", expand=True)

        self._output.tag_configure("go",   foreground=GO_CLR,   font=(FONT_MONO, 12, "bold"))
        self._output.tag_configure("nogo", foreground=NOGO_CLR, font=(FONT_MONO, 12, "bold"))
        self._output.tag_configure("moon", foreground=ACCENT)
        self._output.tag_configure("warn", foreground=WARN_CLR)
        self._output.tag_configure("dim",  foreground=TEXT_DIM)
        self._output.tag_configure("err",  foreground=NOGO_CLR)
        self._output.tag_configure("ok",   foreground=GO_CLR)

    def _start_forecast(self):
        self._run_btn.configure(state="disabled", text="Running…")
        self._clear_output()
        threading.Thread(target=self._run_forecast, daemon=True).start()

    def _run_forecast(self):
        args_list = []
        if self._night_var.get() == "tomorrow":
            args_list.append("--tomorrow")

        site_val = self._site_var.get()
        if site_val != "All sites":
            key = site_val.split(":")[0].strip()
            args_list += ["--site", key]

        if self._dry_run_var.get():
            args_list.append("--dry-run")

        args = build_parser().parse_args(args_list)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_buf, stderr_buf
        try:
            cmd_run(args)
        except SystemExit:
            pass
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        self.after(0, self._display_output,
                   stdout_buf.getvalue(), stderr_buf.getvalue())
        self.after(0, self._run_btn.configure,
                   {"state": "normal", "text": "▶  Run Forecast"})

    def _display_output(self, text: str, errors: str = ""):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")

        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            lo = stripped.lower()
            if "  go " in line or stripped.startswith("GO "):
                tag = "go"
            elif "no-go" in lo or stripped.startswith("NO-GO"):
                tag = "nogo"
            elif stripped.startswith("Moon:") or "rises" in lo or "sets" in lo:
                tag = "moon"
            elif "dry-run" in lo or "skipping email" in lo:
                tag = "warn"
            elif stripped.startswith("Alert sent"):
                tag = "ok"
            elif stripped.endswith("…") or stripped.startswith("Fetching"):
                tag = "dim"
            else:
                tag = ""
            self._output.insert("end", line, tag)

        if errors:
            self._output.insert("end", "\n" + errors, "err")

        self._output.configure(state="disabled")
        self._output.see("end")
        self._set_status("Forecast complete.")

    def _clear_output(self):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

    # ── Sites tab ───────────────────────────────────────────────────────────────

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
        self._tree.bind("<<TreeviewSelect>>", lambda _: self._sync_map_markers())

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

    def _refresh_sites(self):
        if hasattr(self, "_tree"):
            for row in self._tree.get_children():
                self._tree.delete(row)
            try:
                entries = list_sites()
            except FileNotFoundError:
                self._sync_map_markers()
                return
            for key, site, is_active in entries:
                drive  = f"{site.drive_min} min" if site.drive_min else "—"
                active = "★" if is_active else ""
                self._tree.insert("", "end", iid=key,
                                  values=(key, site.name, site.bortle,
                                          drive, site.timezone, active))

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

    def _sync_map_markers(self):
        """Clear and redraw site pins. If a row is selected, show only that site + active site."""
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

        sel = self._tree.selection() if hasattr(self, "_tree") else ()
        selected_key = sel[0] if sel else None
        active_key = next((k for k, _, is_active in entries if is_active), None)
        show_keys = (
            {selected_key, active_key} - {None}
            if selected_key and selected_key != active_key
            else None  # None means show all
        )

        visible = [(k, s) for k, s, _ in entries if show_keys is None or k in show_keys]
        for key, site in visible:
            label = f"{site.name}  (Bortle {site.bortle})"
            self._map_widget.set_marker(
                site.lat, site.lon, text=label,
                command=lambda m, k=key: self._on_map_marker_click(k),  # m absorbs marker obj
            )
        lats = [s.lat for _, s in visible]
        lons = [s.lon for _, s in visible]
        if len(visible) == 1:
            self._map_widget.set_position(lats[0], lons[0], zoom=10)
        else:
            padding = 0.5
            self._map_widget.fit_bounding_box(
                (max(lats) + padding, min(lons) - padding),
                (min(lats) - padding, max(lons) + padding),
            )

    def _on_map_marker_click(self, site_key: str):
        """Switch to Forecast tab and select the given site."""
        self._nb.select(self._tab_forecast)
        if not hasattr(self, "_site_combo"):
            return
        target_option = next(
            (opt for opt in self._site_combo.cget("values")
             if opt.startswith(f"{site_key}:")),
            None,
        )
        if target_option:
            self._site_var.set(target_option)

    def _add_site_dialog(self):
        dlg = SiteDialog(self, title="Add Site")
        self.wait_window(dlg)
        if dlg.result:
            try:
                add_site(**dlg.result)
                self._refresh_sites()
                self._set_status(f"Site '{dlg.result['key']}' added.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    def _edit_site_dialog(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select a site", "Click a site row first.", parent=self)
            return
        key      = sel[0]
        site_map = {k: s for k, s, _ in list_sites()}
        dlg      = SiteDialog(self, title="Edit Site", site=site_map[key], key=key)
        self.wait_window(dlg)
        if dlg.result:
            try:
                add_site(**dlg.result)
                self._refresh_sites()
                self._set_status(f"Site '{key}' updated.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    def _set_active_site(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select a site", "Click a site row first.", parent=self)
            return
        key = sel[0]
        try:
            set_active_site(key)
            self._refresh_sites()
            self._set_status(f"Active site → '{key}'.")
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _delete_site(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Select a site", "Click a site row first.", parent=self)
            return
        key = sel[0]
        if messagebox.askyesno("Delete site",
                                f"Delete '{key}'?  This cannot be undone.",
                                icon="warning", parent=self):
            try:
                delete_site(key)
                self._refresh_sites()
                self._set_status(f"Site '{key}' deleted.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    # ── Schedule tab ────────────────────────────────────────────────────────────

    def _build_schedule_tab(self, parent):
        inner = ttk.Frame(parent)
        inner.pack(expand=True)

        ttk.Label(inner, text="Scheduled Alerts",
                  font=(FONT_PROP, 17, "bold")).pack(pady=(0, 5))
        ttk.Label(inner, text="Installs two daily jobs using your OS native scheduler.",
                  style="Sub.TLabel").pack(pady=(0, 22))

        # Status card
        status_card = ttk.Frame(inner, style="Card.TFrame")
        status_card.pack(fill="x", pady=(0, 18), ipadx=28, ipady=16)

        self._sched_title  = ttk.Label(status_card, style="Card.TLabel",
                                        font=(FONT_PROP, 13, "bold"))
        self._sched_title.pack()
        self._sched_detail = ttk.Label(status_card, style="CardDim.TLabel",
                                        wraplength=520, justify="center")
        self._sched_detail.pack(pady=(5, 0))

        # Job info card
        info_card = ttk.Frame(inner, style="Card.TFrame")
        info_card.pack(fill="x", pady=(0, 26), ipadx=28, ipady=16)

        for time_str, flag, desc in [
            ("6:00 PM", "--tomorrow",    "Tomorrow night's forecast — always sends email"),
            ("2:00 PM", "--only-if-go",  "Tonight's conditions — sends only if a site is GO"),
        ]:
            row = ttk.Frame(info_card, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=time_str, bg=CARD, fg=ACCENT,
                     font=(FONT_MONO, 12, "bold"), width=9,
                     anchor="w").pack(side="left")
            tk.Label(row, text=flag, bg=CARD, fg=TEXT_DIM,
                     font=(FONT_MONO, 12), width=16,
                     anchor="w").pack(side="left")
            tk.Label(row, text=desc, bg=CARD, fg=TEXT,
                     font=(FONT_PROP, 12),
                     anchor="w").pack(side="left", padx=(10, 0))

        btn_row = ttk.Frame(inner)
        btn_row.pack()
        ttk.Button(btn_row, text="Install Schedule", style="Go.TButton",
                   command=self._install_schedule).pack(side="left", padx=(0, 14))
        ttk.Button(btn_row, text="Remove Schedule", style="Danger.TButton",
                   command=self._remove_schedule).pack(side="left")

        self.after(300, self._refresh_schedule_status)

    def _refresh_schedule_status(self):
        try:
            installed, detail = scheduler_setup.get_schedule_status()
        except Exception as e:
            self._sched_title.configure(text="⚠  Could not check status",
                                         foreground=WARN_CLR)
            self._sched_detail.configure(text=str(e))
            return

        if installed:
            self._sched_title.configure(text="✓  Schedule installed",
                                         foreground=GO_CLR)
            self._sched_detail.configure(
                text=detail or "Jobs registered in system scheduler.")
        else:
            self._sched_title.configure(text="✗  Not scheduled",
                                         foreground=NOGO_CLR)
            self._sched_detail.configure(
                text="Click 'Install Schedule' to set up daily alerts.")

    def _install_schedule(self):
        try:
            scheduler_setup.install_schedule()
            self._refresh_schedule_status()
            self._set_status("Schedule installed.")
            messagebox.showinfo("Done", "Daily alerts scheduled successfully.",
                                parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _remove_schedule(self):
        if messagebox.askyesno("Remove schedule",
                                "Remove both scheduled alert jobs?", parent=self):
            try:
                scheduler_setup.uninstall_schedule()
                self._refresh_schedule_status()
                self._set_status("Schedule removed.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    # ── Forecast tab ─────────────────────────────────────────────────────────────

    def _build_forecast_tab(self, parent):
        self._forecast_nights = []

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=26, pady=(20, 0))

        ttk.Label(ctrl, text="Site:", style="Dim.TLabel").pack(side="left")
        self._forecast_site_var   = tk.StringVar(value="")
        self._forecast_site_combo = ttk.Combobox(ctrl, textvariable=self._forecast_site_var,
                                                  state="readonly", width=32,
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

        # ── PanedWindow: night list (top) + detail panel (bottom) ─────────────
        self._forecast_paned = ttk.PanedWindow(parent, orient="vertical")
        self._forecast_paned.pack(fill="both", expand=True, padx=26, pady=(12, 8))

        # Top pane: night treeview
        tree_frame = ttk.Frame(self._forecast_paned)

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
        self._forecast_paned.add(tree_frame, weight=1)

        # ── Detail panel (added to paned on first night selection) ────────────
        self._forecast_detail_shown = False
        self._forecast_detail_pane  = ttk.Frame(self._forecast_paned, style="Card.TFrame")

        # Scrollable canvas so the whole detail section scrolls when space is limited
        _detail_canvas = tk.Canvas(self._forecast_detail_pane, bg=CARD,
                                   highlightthickness=0, bd=0)
        _detail_vsb = ttk.Scrollbar(self._forecast_detail_pane,
                                     orient="vertical", command=_detail_canvas.yview)
        _detail_canvas.configure(yscrollcommand=_detail_vsb.set)
        _detail_vsb.pack(side="right", fill="y")
        _detail_canvas.pack(side="left", fill="both", expand=True)

        _scroll_inner = ttk.Frame(_detail_canvas, style="Card.TFrame")
        _canvas_win   = _detail_canvas.create_window((0, 0), window=_scroll_inner,
                                                      anchor="nw")

        def _on_inner_resize(event):
            _detail_canvas.configure(scrollregion=_detail_canvas.bbox("all"))

        def _on_canvas_resize(event):
            _detail_canvas.itemconfig(_canvas_win, width=event.width)

        _scroll_inner.bind("<Configure>", _on_inner_resize)
        _detail_canvas.bind("<Configure>", _on_canvas_resize)

        def _on_mousewheel(event):
            _detail_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _detail_canvas.bind("<Enter>",
                             lambda _: _detail_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        _detail_canvas.bind("<Leave>",
                             lambda _: _detail_canvas.unbind_all("<MouseWheel>"))

        detail_inner = ttk.Frame(_scroll_inner, style="Card.TFrame")
        detail_inner.pack(fill="x", padx=26, pady=12)

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

        ttk.Label(right, text="Imaging Window  (sunset → sunrise, local time)",
                  style="CardDim.TLabel").pack(anchor="w", pady=(8, 4))
        self._detail_hours_txt = tk.Text(
            right, bg=CARD, fg=TEXT, font=(FONT_MONO, 11),
            relief="flat", bd=0, state="disabled", height=10, width=42,
            padx=4, pady=4,
        )
        self._detail_hours_txt.pack(anchor="w")

        # ── Targets section (hidden until a GO night is selected) ─────────────
        self._target_section_sep   = ttk.Separator(_scroll_inner)
        self._target_section_frame = ttk.Frame(_scroll_inner,
                                                style="Card.TFrame")

        ttk.Label(self._target_section_frame,
                  text="Recommended Targets",
                  style="CardDim.TLabel").pack(anchor="w", padx=26, pady=(8, 4))

        target_cols = ("name", "common_name", "type", "peak_alt",
                       "hrs_vis", "transits", "description")
        self._target_tree = ttk.Treeview(
            self._target_section_frame,
            columns=target_cols, show="headings",
            height=8, selectmode="none",
        )
        self._target_tree.heading("name",        text="Name",        anchor="w")
        self._target_tree.heading("common_name", text="Common Name", anchor="w")
        self._target_tree.heading("type",        text="Type",        anchor="w")
        self._target_tree.heading("peak_alt",    text="Peak Alt",    anchor="center")
        self._target_tree.heading("hrs_vis",     text="Hrs Vis",     anchor="center")
        self._target_tree.heading("transits",    text="Zenith",      anchor="center")
        self._target_tree.heading("description", text="Description", anchor="w")

        self._target_tree.column("name",        width=65,  anchor="w",      stretch=False)
        self._target_tree.column("common_name", width=140, anchor="w",      stretch=False)
        self._target_tree.column("type",        width=120, anchor="w",      stretch=False)
        self._target_tree.column("peak_alt",    width=60,  anchor="center", stretch=False)
        self._target_tree.column("hrs_vis",     width=50,  anchor="center", stretch=False)
        self._target_tree.column("transits",    width=65,  anchor="center", stretch=False)
        self._target_tree.column("description", width=180, anchor="w",      stretch=True)

        self._target_tree.pack(fill="both", expand=True, padx=26, pady=(0, 12))

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

    def _run_forecast_load(self, site_key: str):
        from site_manager import get_active_site
        from weather import fetch_weather_range
        from seeing import fetch_seeing, SeeingResult
        from moon import get_moon_info
        from scorer import score_night
        from target_recommender import get_nightly_targets

        try:
            site         = get_active_site(override=site_key)
            weather_days = fetch_weather_range(site.key, site.lat, site.lon, days=15)
            seeing_all   = fetch_seeing(site.key, site.lat, site.lon)

            seeing_by_time: dict = {}
            if seeing_all.ok:
                for sh in seeing_all.hours:
                    t = sh.time.replace(minute=0, second=0, microsecond=0)
                    seeing_by_time[t] = sh

            nights = []
            for i, (target_date, weather) in enumerate(weather_days[:14]):
                moon   = get_moon_info(site.lat, site.lon, target_date)
                window = _forecast_imaging_window(target_date, site.lat, site.lon)

                # Combine this day's and next day's weather hours so the window
                # can span midnight (sunset often falls on the next UTC date).
                combined_weather_hours = list(weather.hours)
                if i + 1 < len(weather_days):
                    combined_weather_hours.extend(weather_days[i + 1][1].hours)

                night_seeing_hours = [seeing_by_time[t] for t in window
                                       if t in seeing_by_time]

                if night_seeing_hours:
                    night_seeing     = SeeingResult(site_key=site.key,
                                                    fetched_at=seeing_all.fetched_at,
                                                    hours=night_seeing_hours)
                    seeing_available = True
                elif not seeing_all.ok:
                    night_seeing     = SeeingResult(site_key=site.key,
                                                    fetched_at=seeing_all.fetched_at,
                                                    hours=[], error=seeing_all.error)
                    seeing_available = False
                else:
                    night_seeing     = SeeingResult(site_key=site.key,
                                                    fetched_at=seeing_all.fetched_at,
                                                    hours=[],
                                                    error="Beyond 7-day forecast range")
                    seeing_available = False

                score = score_night(weather, night_seeing, moon, site.bortle, target_date)
                window_hours = sorted(
                    [h for h in combined_weather_hours if h.time in window],
                    key=lambda h: h.time,
                )
                targets = get_nightly_targets(site.lat, site.lon, window) if score.go else []
                nights.append({
                    "date":             target_date,
                    "score":            score,
                    "moon":             moon,
                    "weather":          weather,
                    "seeing_available": seeing_available,
                    "lat":              site.lat,
                    "lon":              site.lon,
                    "window_hours":     window_hours,
                    "timezone":         site.timezone,
                    "targets":          targets,
                })

            self.after(0, self._forecast_loaded, nights)
        except Exception as e:
            self.after(0, self._forecast_load_failed, str(e))

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

    def _on_forecast_select(self, _event):
        sel = self._forecast_tree.selection()
        if not sel:
            return
        idx = self._forecast_tree.index(sel[0])
        if idx >= len(self._forecast_nights):
            return
        if not self._forecast_detail_shown:
            self._forecast_paned.add(self._forecast_detail_pane, weight=2)
            self._forecast_detail_shown = True
        self._show_forecast_detail(self._forecast_nights[idx])


    def _show_forecast_detail(self, night: dict):
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

        _SUPPRESS = {"Seeing data unavailable"}
        warnings = [w for w in score.warnings if w not in _SUPPRESS]
        self._detail_warn_lbl.configure(
            text="\n".join(warnings) if warnings else "")

        weather     = night["weather"]
        target_date = night["date"]

        self._detail_hours_txt.configure(state="normal")
        self._detail_hours_txt.delete("1.0", "end")

        night_rows = night.get("window_hours", [])
        tz_name    = night.get("timezone", "UTC")
        try:
            from zoneinfo import ZoneInfo
            local_tz = ZoneInfo(tz_name)
        except Exception:
            local_tz = None

        def _local(dt):
            if local_tz:
                return dt.astimezone(local_tz)
            return dt

        if not weather.ok or not weather.hours:
            self._detail_hours_txt.insert("end", "Weather data unavailable.")
        elif not night_rows:
            self._detail_hours_txt.insert("end", "No hours in imaging window.")
        else:
            tz_label = tz_name.split("/")[-1].replace("_", " ") if local_tz else "UTC"
            self._detail_hours_txt.insert(
                "end", f"{'Hour (' + tz_label + ')':>14}  {'Clouds':>6}  {'Wind':>7}  {'Humidity':>8}\n")
            self._detail_hours_txt.insert("end", "─" * 44 + "\n")

            for h in night_rows:
                local_t = _local(h.time)
                self._detail_hours_txt.insert(
                    "end",
                    f"{local_t.strftime('%a %H:00'):>14}  "
                    f"{h.cloud_cover_pct:>5}%  "
                    f"{h.wind_speed_kmh:>5.0f}km/h  "
                    f"{h.humidity_pct:>6}%\n",
                )

        self._detail_hours_txt.configure(state="disabled")

        targets = night.get("targets", [])
        if targets:
            self._target_section_sep.pack(fill="x")
            self._target_section_frame.pack(fill="both", expand=True)
            self._target_tree.delete(*self._target_tree.get_children())
            for t in targets:
                if t.transit_utc and local_tz:
                    transit_str = _local(t.transit_utc).strftime("%I:%M %p").lstrip("0")
                elif t.transit_utc:
                    transit_str = t.transit_utc.strftime("%I:%M %p").lstrip("0")
                else:
                    transit_str = "—"
                self._target_tree.insert("", "end", values=(
                    t.name,
                    t.common_name,
                    t.type,
                    f"{t.peak_alt_deg:.0f}°",
                    f"{t.hours_visible:.0f}h",
                    transit_str,
                    t.description,
                ))
        else:
            self._target_section_sep.pack_forget()
            self._target_section_frame.pack_forget()

    # ── Chart tab ───────────────────────────────────────────────────────────────

    def _build_chart_tab(self, parent):
        self._chart_data = None

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=26, pady=(20, 0))

        ttk.Label(ctrl, text="Site:", style="Dim.TLabel").pack(side="left")
        self._chart_site_var   = tk.StringVar(value="")
        self._chart_site_combo = ttk.Combobox(ctrl, textvariable=self._chart_site_var,
                                               state="readonly", width=32,
                                               font=(FONT_PROP, 12))
        self._chart_site_combo.pack(side="left", padx=(8, 0))

        self._chart_load_btn = ttk.Button(ctrl, text="Load Chart",
                                           style="Accent.TButton",
                                           command=self._start_chart_load)
        self._chart_load_btn.pack(side="left", padx=(16, 0))

        self._chart_error_var = tk.StringVar(value="")
        self._chart_error_lbl = ttk.Label(ctrl, textvariable=self._chart_error_var,
                                           style="Dim.TLabel", foreground=WARN_CLR)
        self._chart_error_lbl.pack(side="left", padx=(16, 0))

        ttk.Separator(parent).pack(fill="x", pady=(14, 0))

        self._build_chart_legend(parent)

        # ── Canvas + scrollbars ───────────────────────────────────────────────
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        self._chart_canvas = tk.Canvas(frame, bg=BG, highlightthickness=0)
        hbar = ttk.Scrollbar(frame, orient="horizontal",
                              command=self._chart_canvas.xview)
        vbar = ttk.Scrollbar(frame, orient="vertical",
                              command=self._chart_canvas.yview)
        self._chart_canvas.configure(xscrollcommand=hbar.set,
                                      yscrollcommand=vbar.set)
        hbar.pack(side="bottom", fill="x")
        vbar.pack(side="right",  fill="y")
        self._chart_canvas.pack(side="left", fill="both", expand=True)

        # Hover tooltip
        self._chart_tooltip_lbl = tk.Label(
            self, bg="#ffffe0", fg="#000000",
            font=(FONT_MONO, 10), relief="solid", borderwidth=1,
            padx=6, pady=3, justify="left",
        )
        self._chart_canvas.bind("<Motion>", self._on_chart_motion)

        # Mouse-wheel horizontal scroll
        def _on_chart_wheel(e):
            delta = e.delta
            if sys.platform != "darwin":
                delta = delta // 120
            self._chart_canvas.xview_scroll(int(-1 * delta), "units")
        self._chart_canvas.bind("<Enter>", lambda _e: (
            self._chart_canvas.bind_all("<MouseWheel>", _on_chart_wheel),
            self._chart_canvas.bind_all("<Button-4>",
                lambda ev: self._chart_canvas.xview_scroll(-1, "units")),
            self._chart_canvas.bind_all("<Button-5>",
                lambda ev: self._chart_canvas.xview_scroll(1, "units")),
        ))
        self._chart_canvas.bind("<Leave>", lambda _e: (
            self._chart_canvas.unbind_all("<MouseWheel>"),
            self._chart_canvas.unbind_all("<Button-4>"),
            self._chart_canvas.unbind_all("<Button-5>"),
            self._chart_tooltip_lbl.place_forget(),
        ))

        self.after(150, self._refresh_chart_sites)

    def _refresh_chart_sites(self):
        if not hasattr(self, "_chart_site_combo"):
            return
        try:
            from site_manager import list_sites
            entries = list_sites()
        except FileNotFoundError:
            entries = []
        options = [f"{k}: {s.name}" for k, s, _ in entries]
        self._chart_site_combo.configure(values=options)
        if options and not self._chart_site_var.get():
            self._chart_site_var.set(options[0])

    def _start_chart_load(self):
        site_val = self._chart_site_var.get()
        if not site_val:
            return
        self._chart_load_btn.configure(state="disabled", text="Loading…")
        self._chart_error_var.set("")
        self._chart_canvas.delete("all")
        self._chart_data = None
        key = site_val.split(":")[0].strip()
        threading.Thread(target=self._run_chart_load, args=(key,), daemon=True).start()

    def _run_chart_load(self, site_key: str):
        from site_manager import get_active_site
        from chart_html import build_chart_data
        try:
            site = get_active_site(override=site_key)
            data = build_chart_data(site, hours=72)
            self.after(0, self._chart_loaded, data)
        except Exception as e:
            self.after(0, self._chart_load_failed, str(e))

    def _chart_loaded(self, data):
        self._chart_data = data
        self._chart_load_btn.configure(state="normal", text="Load Chart")
        if data.errors:
            self._chart_error_var.set("⚠ " + " / ".join(data.errors))
        self._draw_chart(data)
        self._set_status("Chart loaded.")

    def _chart_load_failed(self, msg: str):
        self._chart_load_btn.configure(state="normal", text="Load Chart")
        self._chart_error_var.set(f"Error: {msg}")
        self._set_status("Chart load failed.")

    def _build_chart_legend(self, parent):
        from chart_html import (cloud_color, wind_color, temperature_color,
                                 precipitation_color, moon_color, _MISSING)

        outer = ttk.Frame(parent)
        outer.pack(fill="x", padx=26, pady=(8, 4))

        SWATCH_W = 26
        SWATCH_H = 13

        def swatch_group(title, entries):
            grp = tk.Frame(outer, bg=BG)
            grp.pack(side="left", padx=(0, 20), anchor="n")
            tk.Label(grp, text=title, bg=BG, fg=TEXT_DIM,
                     font=(FONT_PROP, 8)).pack(anchor="w")
            row = tk.Frame(grp, bg=BG)
            row.pack(anchor="w")
            for i, (color, lbl) in enumerate(entries):
                if i > 0:
                    tk.Label(row, text="→", bg=BG, fg=TEXT_DIM,
                             font=(FONT_PROP, 8)).pack(side="left")
                tk.Frame(row, bg=color, width=SWATCH_W,
                         height=SWATCH_H).pack(side="left")
                if lbl:
                    tk.Label(row, text=lbl, bg=BG, fg=TEXT_DIM,
                             font=(FONT_PROP, 8)).pack(side="left", padx=(2, 0))

        swatch_group("Cloud / Seeing / Transp / Humidity", [
            (cloud_color(0),   "Good"),
            (cloud_color(50),  ""),
            (cloud_color(100), "Poor"),
        ])
        swatch_group("Wind", [
            (wind_color(0),  "Calm"),
            (wind_color(20), ""),
            (wind_color(40), "Strong"),
        ])
        swatch_group("Temperature", [
            (temperature_color(-15), "Cold"),
            (temperature_color(5),   "Mild"),
            (temperature_color(30),  "Warm"),
        ])
        swatch_group("Precip", [
            (precipitation_color(0), "Dry"),
            (precipitation_color(1), "Rain"),
        ])
        swatch_group("Moon", [
            (moon_color(0),   "New"),
            (moon_color(100), "Full"),
        ])
        swatch_group("No data", [
            (_MISSING, "—"),
        ])

    def _draw_chart(self, data):
        from chart_html import (cloud_color, seeing_color, transparency_color,
                                 wind_color, humidity_color, temperature_color,
                                 precipitation_color, moon_color, _MISSING)
        from datetime import timedelta

        canvas = self._chart_canvas
        canvas.delete("all")

        LABEL_W  = 130
        HEADER_H = 52   # date row (26px) + hour row (26px)
        CELL_W   = 18
        CELL_H   = 28
        hours    = len(data.cloud)

        ROW_DEFS = [
            ("Cloud Cover",  data.cloud,         cloud_color,         lambda v: f"{v}%"),
            ("Seeing",       data.seeing,        seeing_color,        lambda v: f"{v:.0f}/8"),
            ("Transparency", data.transparency,  transparency_color,  lambda v: f"{v:.0f}/8"),
            ("Wind",         data.wind,          wind_color,          lambda v: f"{v:.0f} km/h"),
            ("Humidity",     data.humidity,      humidity_color,      lambda v: f"{v}%"),
            ("Temperature",  data.temperature,   temperature_color,   lambda v: f"{v:.1f}°C"),
            ("Precip",       data.precipitation, precipitation_color, lambda v: f"{v:.1f} mm"),
            ("Moon",         data.moon_pct,      moon_color,          lambda v: f"{v}%"),
        ]

        total_w = LABEL_W + hours * CELL_W + 20
        total_h = HEADER_H + len(ROW_DEFS) * CELL_H + 20
        canvas.configure(scrollregion=(0, 0, total_w, total_h))

        # ── Date headers ──────────────────────────────────────────────────────
        for day in range(3):
            dt = data.start_dt + timedelta(hours=day * 24)
            label = dt.strftime("%a %b %-d")
            x = LABEL_W + day * 24 * CELL_W + 12 * CELL_W
            canvas.create_text(x, 13, text=label, fill=ACCENT,
                               font=(FONT_PROP, 10, "bold"), anchor="center")

        # ── Hour labels ───────────────────────────────────────────────────────
        for i in range(hours):
            if i % 3 == 0:
                h = i % 24
                x = LABEL_W + i * CELL_W + CELL_W // 2
                canvas.create_text(x, 38, text=f"{h:02d}", fill=TEXT_DIM,
                                   font=(FONT_MONO, 8), anchor="center")

        # ── Data rows ─────────────────────────────────────────────────────────
        for row_idx, (label, values, color_fn, _fmt) in enumerate(ROW_DEFS):
            y0 = HEADER_H + row_idx * CELL_H

            # Row label
            canvas.create_text(LABEL_W - 8, y0 + CELL_H // 2,
                               text=label, fill=TEXT_DIM,
                               font=(FONT_PROP, 10), anchor="e")

            # Cells
            for col_idx, val in enumerate(values):
                x0 = LABEL_W + col_idx * CELL_W
                bg = _MISSING if val is None else color_fn(val)
                canvas.create_rectangle(x0, y0, x0 + CELL_W, y0 + CELL_H,
                                        fill=bg, outline="", width=0)

                # Moon rise/set symbols
                if label == "Moon" and col_idx in data.moon_events:
                    sym = "▲" if data.moon_events[col_idx] == "rise" else "▼"
                    canvas.create_text(x0 + CELL_W // 2, y0 + CELL_H // 2,
                                       text=sym, fill="#ffffff",
                                       font=(FONT_PROP, 8))

    def _on_chart_motion(self, event):
        from datetime import timedelta

        data = self._chart_data
        if data is None:
            return

        cx = self._chart_canvas.canvasx(event.x)
        cy = self._chart_canvas.canvasy(event.y)

        LABEL_W  = 130
        HEADER_H = 52
        CELL_W   = 18
        CELL_H   = 28

        col = int((cx - LABEL_W) / CELL_W)
        row = int((cy - HEADER_H) / CELL_H)

        ROW_FIELDS = ["cloud", "seeing", "transparency", "wind",
                      "humidity", "temperature", "precipitation", "moon_pct"]
        ROW_LABELS = ["Cloud Cover", "Seeing", "Transparency", "Wind",
                      "Humidity", "Temperature", "Precip", "Moon"]
        ROW_FMTS   = [
            lambda v: f"{v}%",
            lambda v: f"{v:.0f}/8",
            lambda v: f"{v:.0f}/8",
            lambda v: f"{v:.0f} km/h",
            lambda v: f"{v}%",
            lambda v: f"{v:.1f}°C",
            lambda v: f"{v:.1f} mm",
            lambda v: f"{v}%",
        ]

        if col < 0 or col >= len(data.cloud) or row < 0 or row >= len(ROW_FIELDS):
            self._chart_tooltip_lbl.place_forget()
            return

        val = getattr(data, ROW_FIELDS[row])[col]
        label = ROW_LABELS[row]
        dt = data.start_dt + timedelta(hours=col)
        time_str = dt.strftime("%a %H:00 UTC")

        tip = f"{label}\n{time_str}\n" + ("N/A" if val is None else ROW_FMTS[row](val))
        self._chart_tooltip_lbl.configure(text=tip)
        tx = event.x_root - self.winfo_rootx() + 14
        ty = event.y_root - self.winfo_rooty() + 14
        self._chart_tooltip_lbl.place(x=tx, y=ty)
        self._chart_tooltip_lbl.lift()

    # ── Scoring tab ─────────────────────────────────────────────────────────────

    def _build_scoring_tab(self, parent):
        from scoring_weights import ScoringWeights, load_weights, save_weights

        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        _win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_win, width=e.width))

        def _on_mousewheel(e):
            delta = e.delta
            if sys.platform != "darwin":
                delta = delta // 120
            canvas.yview_scroll(int(-1 * delta), "units")
        canvas.bind("<Enter>", lambda e: (
            canvas.bind_all("<Button-4>", lambda ev: canvas.yview_scroll(-1, "units")),
            canvas.bind_all("<Button-5>", lambda ev: canvas.yview_scroll(1, "units")),
            canvas.bind_all("<MouseWheel>", _on_mousewheel),
        ))
        canvas.bind("<Leave>", lambda e: (
            canvas.unbind_all("<Button-4>"),
            canvas.unbind_all("<Button-5>"),
            canvas.unbind_all("<MouseWheel>"),
        ))

        ttk.Label(inner, text="Scoring Weights",
                  font=(FONT_PROP, 17, "bold")).pack(pady=(0, 5))
        ttk.Label(inner,
                  text="Adjust how each factor contributes to the go/no-go score. "
                       "Relative values — normalized automatically.",
                  style="Sub.TLabel").pack(pady=(0, 22))

        defaults = ScoringWeights()
        current = load_weights()

        self._scoring_vars: dict[str, tk.IntVar] = {}
        for field in vars(defaults):
            self._scoring_vars[field] = tk.IntVar(value=getattr(current, field))

        def _make_section(title, fields):
            lf = ttk.LabelFrame(inner, text=title, padding=(16, 8))
            lf.pack(fill="x", padx=24, pady=(0, 16))
            lf.columnconfigure(1, weight=1)
            for row, (label, field) in enumerate(fields):
                var = self._scoring_vars[field]
                ttk.Label(lf, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
                val_lbl = ttk.Label(lf, text=str(var.get()), width=4, anchor="e")
                val_lbl.grid(row=row, column=2, padx=(8, 0), pady=4)

                def _trace(name, *_, v=var, lbl=val_lbl):
                    lbl.configure(text=str(v.get()))

                var.trace_add("write", _trace)
                ttk.Scale(
                    lf, from_=0, to=100,
                    orient="horizontal",
                    variable=var,
                    command=lambda val, v=var: v.set(int(float(val))),
                ).grid(row=row, column=1, sticky="ew", pady=4)

        _make_section("Top-Level Weights", [
            ("Weather", "weather_weight"),
            ("Seeing",  "seeing_weight"),
            ("Moon",    "moon_weight"),
        ])
        _make_section("Weather Sub-Weights", [
            ("Cloud Cover",    "cloud_weight"),
            ("Wind",           "wind_weight"),
            ("Humidity / Dew", "dew_weight"),
        ])
        _make_section("Seeing Sub-Weights", [
            ("Seeing Quality", "seeing_quality_weight"),
            ("Transparency",   "transparency_weight"),
        ])
        _make_section("Moon Sub-Weights", [
            ("Moon Phase",               "phase_weight"),
            ("Dark Hours After Moonset", "dark_hours_weight"),
        ])
        _make_section("GO Threshold", [
            ("Min score to send GO alert", "go_threshold"),
        ])

        btn_row = ttk.Frame(inner)
        btn_row.pack(fill="x", padx=24, pady=(8, 24))

        self._scoring_status = tk.StringVar(value="")
        ttk.Label(btn_row, textvariable=self._scoring_status,
                  style="Dim.TLabel").pack(side="left")

        def _reset():
            d = ScoringWeights()
            for field, var in self._scoring_vars.items():
                var.set(getattr(d, field))
            self._scoring_status.set("Reset to defaults — click Save to apply.")

        def _save():
            w = ScoringWeights(**{f: v.get() for f, v in self._scoring_vars.items()})
            save_weights(w)
            self._scoring_status.set("Saved.")
            self.after(3000, lambda: self._scoring_status.set(""))

        ttk.Button(btn_row, text="Reset to Defaults", command=_reset).pack(side="left", padx=(8, 0))
        ttk.Button(btn_row, text="Save", style="Go.TButton", command=_save).pack(side="right")

    # ── Settings tab ────────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        _win = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_win, width=e.width))

        def _on_mousewheel(e):
            delta = e.delta
            if sys.platform != "darwin":
                delta = delta // 120
            canvas.yview_scroll(int(-1 * delta), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        # Linux trackpad/wheel
        canvas.bind("<Enter>", lambda e: (
            canvas.bind_all("<Button-4>", lambda ev: canvas.yview_scroll(-1, "units")),
            canvas.bind_all("<Button-5>", lambda ev: canvas.yview_scroll(1, "units")),
            canvas.bind_all("<MouseWheel>", _on_mousewheel),
        ))
        canvas.bind("<Leave>", lambda e: (
            canvas.unbind_all("<Button-4>"),
            canvas.unbind_all("<Button-5>"),
            canvas.unbind_all("<MouseWheel>"),
        ))

        ttk.Label(inner, text="Email Credentials",
                  font=(FONT_PROP, 17, "bold")).pack(pady=(0, 5))
        ttk.Label(inner,
                  text="Used to send nightly go/no-go alerts. Credentials are stored locally.",
                  style="Sub.TLabel").pack(pady=(0, 22))

        card = ttk.Frame(inner, style="Card.TFrame")
        card.pack(fill="x", ipadx=28, ipady=20)
        card.columnconfigure(1, weight=1)

        self._cred_user_var = tk.StringVar()
        self._cred_pass_var = tk.StringVar()
        self._cred_to_var   = tk.StringVar()
        self._pass_shown    = False

        fields = [
            ("Email used to send alerts", self._cred_user_var, False),
            ("App password",     self._cred_pass_var, True),
            ("Alert recipient",  self._cred_to_var,   False),
        ]
        for row_idx, (label, var, is_pass) in enumerate(fields):
            ttk.Label(card, text=label + ":", style="CardDim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=8, padx=(16, 12))
            entry = ttk.Entry(card, textvariable=var, font=(FONT_PROP, 12), width=36,
                              show="•" if is_pass else "")
            entry.grid(row=row_idx, column=1, sticky="ew", pady=8)
            entry.bind("<FocusOut>", lambda e: self._save_credentials(silent=True))
            if is_pass:
                self._pass_entry = entry
                ttk.Button(card, text="Show", width=6,
                           command=self._toggle_password).grid(
                    row=row_idx, column=2, padx=(8, 16), pady=8)

        ttk.Label(card,
                  text="Tip: use an App Password or your provider's equivalent, not your login password.",
                  style="CardDim.TLabel").grid(
            row=len(fields), column=0, columnspan=3, pady=(4, 0), padx=16)

        self._smtp_custom_var = tk.BooleanVar(value=False)
        self._smtp_host_var   = tk.StringVar(value="smtp.gmail.com")
        self._smtp_port_var   = tk.StringVar(value="587")

        smtp_toggle_frame = ttk.Frame(inner)
        smtp_toggle_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            smtp_toggle_frame,
            text="Use a different email provider (custom SMTP)",
            variable=self._smtp_custom_var,
            command=self._on_smtp_toggle,
        ).pack(anchor="w", padx=16)

        self._smtp_detail_frame = ttk.Frame(inner, style="Card.TFrame")
        self._smtp_detail_frame.columnconfigure(1, weight=1)
        self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
        self._smtp_detail_frame.pack_forget()
        for row_idx, (label, var) in enumerate([
            ("SMTP host", self._smtp_host_var),
            ("SMTP port", self._smtp_port_var),
        ]):
            ttk.Label(self._smtp_detail_frame, text=label + ":", style="CardDim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=8, padx=(16, 12))
            smtp_entry = ttk.Entry(self._smtp_detail_frame, textvariable=var,
                                   font=(FONT_PROP, 12), width=36)
            smtp_entry.grid(row=row_idx, column=1, sticky="ew", pady=8)
            smtp_entry.bind("<FocusOut>", lambda e: self._save_credentials(silent=True))

        btn_row = ttk.Frame(inner)
        btn_row.pack(pady=(20, 0))
        ttk.Button(btn_row, text="Save Credentials", style="Accent.TButton",
                   command=self._save_credentials).pack(side="left", padx=(0, 14))
        self._test_btn = ttk.Button(btn_row, text="Send Test Email",
                                     command=self._send_test_email)
        self._test_btn.pack(side="left")

        # ── Email Format ───────────────────────────────────────────────────────────
        ttk.Separator(inner).pack(fill="x", pady=(24, 0))
        ttk.Label(inner, text="Email Format",
                  font=(FONT_PROP, 15, "bold")).pack(pady=(16, 4))
        ttk.Label(inner,
                  text="Choose how alert emails are sent.",
                  style="Sub.TLabel").pack(pady=(0, 16))

        fmt_card = ttk.Frame(inner, style="Card.TFrame")
        fmt_card.pack(fill="x", ipadx=28, ipady=16)

        self._email_format_var = tk.StringVar(value="plain")
        ttk.Radiobutton(fmt_card, text="Plain text  (current behavior)",
                         variable=self._email_format_var,
                         value="plain").pack(anchor="w", padx=16, pady=(8, 4))
        ttk.Radiobutton(fmt_card, text="HTML with chart  (color-coded 72-hour grid)",
                         variable=self._email_format_var,
                         value="html").pack(anchor="w", padx=16, pady=(0, 8))

        self._loading_email_format = False

        def _on_email_format_change(*_):
            if getattr(self, "_loading_email_format", False):
                return
            from data_dir import ENV_FILE
            from dotenv import set_key
            ENV_FILE.touch()
            set_key(ENV_FILE, "EMAIL_FORMAT", self._email_format_var.get())

        self._email_format_var.trace_add("write", _on_email_format_change)

        # ── Home Location ──────────────────────────────────────────────────────
        ttk.Separator(inner).pack(fill="x", pady=(24, 0))
        ttk.Label(inner, text="Home Location",
                  font=(FONT_PROP, 15, "bold")).pack(pady=(16, 4))
        ttk.Label(inner, text="Your starting point for drive-time calculations.",
                  style="Sub.TLabel").pack(pady=(0, 16))

        home_card = ttk.Frame(inner, style="Card.TFrame")
        home_card.pack(fill="x", ipadx=28, ipady=16)
        home_card.columnconfigure(1, weight=1)

        self._home_geo_results: list[dict] = []
        self._home_search_var  = tk.StringVar()
        self._home_lat_var     = tk.StringVar()
        self._home_lon_var     = tk.StringVar()
        self._home_status_var  = tk.StringVar()

        ttk.Label(home_card, text="Search:", style="CardDim.TLabel").grid(
            row=0, column=0, sticky="w", pady=8, padx=(16, 12))
        home_entry = ttk.Entry(home_card, textvariable=self._home_search_var,
                               font=(FONT_PROP, 12))
        home_entry.grid(row=0, column=1, sticky="ew", pady=8)
        home_entry.bind("<Return>", lambda _e: self._search_home_location())
        self._home_search_btn = ttk.Button(home_card, text="Search", width=8,
                                            command=self._search_home_location)
        self._home_search_btn.grid(row=0, column=2, padx=(8, 4), pady=8)
        self._home_detect_btn = ttk.Button(home_card, text="Detect", width=8,
                                            command=self._detect_home_location)
        self._home_detect_btn.grid(row=0, column=3, padx=(0, 16), pady=8)

        self._home_results_var   = tk.StringVar()
        self._home_results_combo = ttk.Combobox(home_card,
                                                 textvariable=self._home_results_var,
                                                 state="disabled",
                                                 font=(FONT_PROP, 11))
        self._home_results_combo.grid(row=1, column=0, columnspan=4,
                                       sticky="ew", padx=16, pady=(0, 8))
        self._home_results_combo.bind("<<ComboboxSelected>>",
                                       self._on_home_result_selected)

        for row_idx, (label, var) in enumerate([("Latitude",  self._home_lat_var),
                                                 ("Longitude", self._home_lon_var)], start=2):
            ttk.Label(home_card, text=label + ":", style="CardDim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=6, padx=(16, 12))
            ttk.Entry(home_card, textvariable=var, font=(FONT_PROP, 12),
                      width=18).grid(row=row_idx, column=1, sticky="w", pady=6)

        home_btn_row = ttk.Frame(inner)
        home_btn_row.pack(pady=(14, 4))
        ttk.Button(home_btn_row, text="Save Home Location", style="Accent.TButton",
                   command=self._save_home_location).pack()
        ttk.Label(inner, textvariable=self._home_status_var,
                  style="Dim.TLabel").pack(pady=(4, 24))

        self.after(50, self._load_credentials_to_form)
        self.after(100, lambda: canvas.configure(scrollregion=canvas.bbox("all")))

    def _load_credentials_to_form(self):
        from data_dir import ENV_FILE
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
        smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
        self._cred_user_var.set(smtp_user)
        self._cred_pass_var.set(smtp_pass)
        self._cred_to_var.set(vals.get("ALERT_EMAIL_TO", ""))
        self._home_lat_var.set(vals.get("HOME_LAT", ""))
        self._home_lon_var.set(vals.get("HOME_LON", ""))
        smtp_host = vals.get("SMTP_HOST", "")
        if smtp_host and smtp_host != "smtp.gmail.com":
            self._smtp_custom_var.set(True)
            self._smtp_host_var.set(smtp_host)
            self._smtp_port_var.set(vals.get("SMTP_PORT", "587"))
            self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
        if hasattr(self, "_email_format_var"):
            self._loading_email_format = True
            self._email_format_var.set(vals.get("EMAIL_FORMAT", "plain"))
            self._loading_email_format = False

    def _save_credentials(self, silent=False):
        import unicodedata
        from data_dir import ENV_FILE
        from dotenv import set_key, unset_key
        def _norm(s): return unicodedata.normalize("NFKC", s).strip()
        smtp_user = _norm(self._cred_user_var.get())
        smtp_pass = _norm(self._cred_pass_var.get())
        alert_to  = _norm(self._cred_to_var.get())
        ENV_FILE.touch()
        if smtp_user:
            set_key(ENV_FILE, "SMTP_USER", smtp_user)
        if smtp_pass:
            set_key(ENV_FILE, "SMTP_PASSWORD", smtp_pass)
        if alert_to:
            set_key(ENV_FILE, "ALERT_EMAIL_TO", alert_to)
        else:
            unset_key(ENV_FILE, "ALERT_EMAIL_TO")
        if self._smtp_custom_var.get():
            smtp_host = _norm(self._smtp_host_var.get()) or "smtp.gmail.com"
            smtp_port = _norm(self._smtp_port_var.get()) or "587"
            set_key(ENV_FILE, "SMTP_HOST", smtp_host)
            set_key(ENV_FILE, "SMTP_PORT", smtp_port)
        else:
            unset_key(ENV_FILE, "SMTP_HOST")
            unset_key(ENV_FILE, "SMTP_PORT")
        self._refresh_cred_banner()
        self._set_status("Credentials saved.")
        if not silent:
            messagebox.showinfo("Saved", "Credentials saved. Send a test email to verify.",
                                parent=self)

    def _search_home_location(self):
        query = self._home_search_var.get().strip()
        if not query:
            return
        self._home_search_btn.configure(state="disabled", text="…")
        threading.Thread(target=self._do_geocode_home, args=(query,),
                         daemon=True).start()

    def _do_geocode_home(self, query: str):
        import requests
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 5},
                headers={"User-Agent": "AstroAlert/1.0 paulydavis@gmail.com"},
                timeout=10,
            )
            resp.raise_for_status()
            self.after(0, self._geocode_home_done, resp.json())
        except Exception as e:
            self.after(0, self._geocode_home_error, str(e))

    def _geocode_home_done(self, results: list[dict]):
        self._home_search_btn.configure(state="normal", text="Search")
        if not results:
            messagebox.showinfo("No results", "No locations found.", parent=self)
            return
        self._home_geo_results = results
        self._home_results_combo.configure(
            values=[r["display_name"] for r in results],
            state="readonly",
        )
        self._home_results_combo.current(0)
        self._on_home_result_selected()

    def _geocode_home_error(self, msg: str):
        self._home_search_btn.configure(state="normal", text="Search")
        messagebox.showerror("Search failed", f"Could not reach geocoding service:\n{msg}",
                             parent=self)

    def _on_home_result_selected(self, _event=None):
        idx = self._home_results_combo.current()
        if idx < 0 or idx >= len(self._home_geo_results):
            return
        r = self._home_geo_results[idx]
        self._home_lat_var.set(f"{float(r['lat']):.5f}")
        self._home_lon_var.set(f"{float(r['lon']):.5f}")

    def _save_home_location(self):
        from data_dir import ENV_FILE
        from dotenv import set_key
        try:
            lat = float(self._home_lat_var.get().strip())
            lon = float(self._home_lon_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid", "Enter valid latitude and longitude.",
                                 parent=self)
            return
        ENV_FILE.touch()
        set_key(ENV_FILE, "HOME_LAT", str(lat))
        set_key(ENV_FILE, "HOME_LON", str(lon))
        self._set_status("Home location saved.")
        messagebox.showinfo("Saved",
                            f"Home set to {lat:.4f}, {lon:.4f}.\n"
                            "Drive times will now calculate automatically when adding sites.",
                            parent=self)

    def _detect_home_location(self):
        self._home_status_var.set("")
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

    def _toggle_password(self):
        self._pass_shown = not self._pass_shown
        self._pass_entry.configure(show="" if self._pass_shown else "•")

    def _on_smtp_toggle(self):
        if self._smtp_custom_var.get():
            self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
        else:
            self._smtp_detail_frame.pack_forget()

    def _send_test_email(self):
        self._test_btn.configure(state="disabled", text="Sending…")
        threading.Thread(target=self._do_test_email, daemon=True).start()

    def _do_test_email(self):
        from smtp_notifier import send_test_email
        result = send_test_email()
        self.after(0, self._test_email_done, result)

    def _test_email_done(self, result):
        self._test_btn.configure(state="normal", text="Send Test Email")
        if result.sent:
            messagebox.showinfo("Success", "Test email sent! Check your inbox.", parent=self)
            self._set_status("Test email sent.")
        else:
            messagebox.showerror("Failed", result.error or "Unknown error.", parent=self)
            self._set_status("Test email failed.")

    def _refresh_cred_banner(self):
        from data_dir import ENV_FILE
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
        smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
        has_creds = bool(smtp_user and smtp_pass)
        if has_creds:
            self._cred_warn.pack_forget()
        else:
            self._cred_warn.pack(fill="x", padx=0, pady=0, before=self._ctrl_frame)

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

    # ── Status bar ──────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=STATUS_BG, height=28)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self._status_var,
                  style="Status.TLabel").pack(side="left", padx=16, pady=4)

    def _set_status(self, msg: str):
        self._status_var.set(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Site add / edit dialog
# ─────────────────────────────────────────────────────────────────────────────

class SiteDialog(tk.Toplevel):
    # (field_key, label, type, required)
    _FIELDS = [
        ("key",         "Key",             str,   True),
        ("name",        "Name",            str,   True),
        ("lat",         "Latitude",        float, True),
        ("lon",         "Longitude",       float, True),
        ("elevation_m", "Elevation (m)",   float, True),
        ("bortle",      "Bortle  (1–9)",   int,   True),
        ("timezone",    "Timezone (IANA)", str,   True),
        ("drive_min",   "Drive (min)",     int,   False),
        ("notes",       "Notes",           str,   False),
    ]

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

    def _build(self, site, key):
        # ── Fixed footer (packed first so it's always visible) ─────────────────
        footer = ttk.Frame(self)
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer).pack(fill="x")
        btns = ttk.Frame(footer)
        btns.pack(pady=12)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=(0, 14))
        ttk.Button(btns, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="left")

        # ── Scrollable body ────────────────────────────────────────────────────
        canvas = tk.Canvas(self, highlightthickness=0, bg=BG)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        _win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_win, width=e.width))

        def _on_mousewheel(e):
            delta = e.delta
            if sys.platform != "darwin":
                delta = delta // 120
            canvas.yview_scroll(int(-1 * delta), "units")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))
        if sys.platform == "linux":
            canvas.bind("<Enter>", lambda _: (
                canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units")),
                canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units")),
            ))

        ttk.Label(inner, text=self.title(),
                  font=(FONT_PROP, 15, "bold")).pack(pady=(20, 0))
        ttk.Separator(inner).pack(fill="x", padx=30, pady=12)

        # ── Location search ────────────────────────────────────────────────────
        sf = ttk.Frame(inner)
        sf.pack(padx=36, fill="x")
        sf.columnconfigure(0, weight=1)

        ttk.Label(sf, text="Search location:", style="Dim.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self._search_var = tk.StringVar()
        se = ttk.Entry(sf, textvariable=self._search_var, font=(FONT_PROP, 12))
        se.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        se.bind("<Return>", lambda _e: self._search_location())

        self._search_btn = ttk.Button(sf, text="Search", width=8,
                                       command=self._search_location)
        self._search_btn.grid(row=1, column=1)

        self._results_var   = tk.StringVar(value="— search above to auto-fill fields —")
        self._results_combo = ttk.Combobox(sf, textvariable=self._results_var,
                                            state="disabled", font=(FONT_PROP, 11))
        self._results_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._results_combo.bind("<<ComboboxSelected>>", self._on_result_selected)

        ttk.Separator(inner).pack(fill="x", padx=30, pady=12)

        # ── Fields grid ────────────────────────────────────────────────────────
        defaults = {
            "key":         key or "",
            "name":        getattr(site, "name",        "") or "",
            "lat":         str(getattr(site, "lat", "")) if site else (
                               f"{self._prefill_lat:.6f}" if self._prefill_lat is not None else ""),
            "lon":         str(getattr(site, "lon", "")) if site else (
                               f"{self._prefill_lon:.6f}" if self._prefill_lon is not None else ""),
            "elevation_m": str(getattr(site, "elevation_m", "")) if site else "",
            "bortle":      str(getattr(site, "bortle",  "")) if site else "",
            "timezone":    getattr(site, "timezone", "America/New_York") or "America/New_York",
            "drive_min":   str(site.drive_min) if (site and site.drive_min) else "",
            "notes":       getattr(site, "notes", "") or "",
        }

        grid = ttk.Frame(inner)
        grid.pack(padx=36, fill="x")
        grid.columnconfigure(1, weight=1)

        self._vars: dict[str, tk.StringVar] = {}
        for row_idx, (field, label, _, _req) in enumerate(self._FIELDS):
            ttk.Label(grid, text=label + ":", style="Dim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=5, padx=(0, 8))
            var   = tk.StringVar(value=defaults[field])
            state = "disabled" if (field == "key" and key) else "normal"
            ttk.Entry(grid, textvariable=var, font=(FONT_PROP, 12),
                      state=state).grid(row=row_idx, column=1, sticky="ew", pady=5)
            self._vars[field] = var

            if field == "drive_min":
                self._calc_btn = ttk.Button(grid, text="Calculate ↗", width=12,
                                             command=self._calculate_drive_time)
                self._calc_btn.grid(row=row_idx, column=2, padx=(8, 0), pady=5)

            if field == "bortle":
                ttk.Button(grid, text="Map ↗", width=6,
                           command=self._open_bortle_map).grid(
                    row=row_idx, column=2, padx=(8, 0), pady=5)

        # ── Active-site checkbox ───────────────────────────────────────────────
        self._set_active_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Set as active site",
                         variable=self._set_active_var).pack(pady=(10, 20))

    # ── Geocoding ──────────────────────────────────────────────────────────────

    def _search_location(self):
        query = self._search_var.get().strip()
        if not query:
            return
        self._search_btn.configure(state="disabled", text="…")
        threading.Thread(target=self._do_geocode, args=(query,), daemon=True).start()

    def _do_geocode(self, query: str):
        import requests
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 5},
                headers={"User-Agent": "AstroAlert/1.0 paulydavis@gmail.com"},
                timeout=10,
            )
            resp.raise_for_status()
            self.after(0, self._geocode_done, resp.json())
        except Exception as e:
            self.after(0, self._geocode_error, str(e))

    def _geocode_done(self, results: list[dict]):
        self._search_btn.configure(state="normal", text="Search")
        if not results:
            messagebox.showinfo("No results",
                                "No locations found — try a more specific name.",
                                parent=self)
            return
        self._geo_results = results
        self._results_combo.configure(
            values=[r["display_name"] for r in results],
            state="readonly",
        )
        self._results_combo.current(0)
        self._on_result_selected()

    def _geocode_error(self, msg: str):
        self._search_btn.configure(state="normal", text="Search")
        messagebox.showerror("Search failed",
                             f"Could not reach geocoding service:\n{msg}",
                             parent=self)

    def _on_result_selected(self, _event=None):
        idx = self._results_combo.current()
        if idx < 0 or idx >= len(self._geo_results):
            return
        r   = self._geo_results[idx]
        lat = float(r["lat"])
        lon = float(r["lon"])

        self._vars["lat"].set(f"{lat:.5f}")
        self._vars["lon"].set(f"{lon:.5f}")

        short_name = r["display_name"].split(",")[0].strip()
        self._vars["name"].set(short_name)

        if not self._editing_key:
            auto_key = re.sub(r"[^a-z0-9]+", "_", short_name.lower()).strip("_")[:24]
            self._vars["key"].set(auto_key)

        threading.Thread(target=self._fetch_elevation,
                         args=(lat, lon), daemon=True).start()

    def _fetch_elevation(self, lat: float, lon: float):
        import requests
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/elevation",
                params={"latitude": lat, "longitude": lon},
                timeout=10,
            )
            resp.raise_for_status()
            elev = resp.json()["elevation"][0]
            self.after(0, self._vars["elevation_m"].set, f"{elev:.0f}")
        except Exception:
            pass  # user can fill it manually

    def _calculate_drive_time(self):
        try:
            site_lat = float(self._vars["lat"].get())
            site_lon = float(self._vars["lon"].get())
        except ValueError:
            messagebox.showwarning("Missing coordinates",
                                   "Fill in latitude and longitude first.",
                                   parent=self)
            return
        home = _get_home_location()
        if home is None:
            messagebox.showwarning("Home not set",
                                   "Set your home location in Settings first.",
                                   parent=self)
            return
        self._calc_btn.configure(state="disabled", text="…")
        home_lat, home_lon = home
        threading.Thread(target=self._do_calculate_drive_time,
                         args=(home_lat, home_lon, site_lat, site_lon),
                         daemon=True).start()

    def _do_calculate_drive_time(self, home_lat, home_lon, site_lat, site_lon):
        try:
            minutes = _osrm_drive_minutes(home_lat, home_lon, site_lat, site_lon)
            self.after(0, self._drive_time_done, minutes, None)
        except Exception as e:
            self.after(0, self._drive_time_done, None, str(e))

    def _drive_time_done(self, minutes, error):
        self._calc_btn.configure(state="normal", text="Calculate ↗")
        if error:
            messagebox.showerror("Routing failed",
                                 f"Could not calculate drive time:\n{error}",
                                 parent=self)
            return
        self._vars["drive_min"].set(str(minutes))

    def _open_bortle_map(self):
        try:
            lat = float(self._vars["lat"].get())
            lon = float(self._vars["lon"].get())
            url = f"https://www.lightpollutionmap.info/#zoom=10&lat={lat}&lon={lon}"
        except ValueError:
            url = "https://www.lightpollutionmap.info/"
        webbrowser.open(url)

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save(self):
        try:
            result: dict = {}
            for field, label, typ, required in self._FIELDS:
                raw = self._vars[field].get().strip()
                if not raw:
                    if required:
                        raise ValueError(f"{label} is required.")
                    result[field] = None
                else:
                    try:
                        result[field] = typ(raw)
                    except (ValueError, TypeError):
                        raise ValueError(f"{label} must be a valid {typ.__name__}.")

            if not 1 <= result.get("bortle", 0) <= 9:
                raise ValueError("Bortle must be between 1 and 9.")

            result["set_active"] = self._set_active_var.get()
            if self._editing_key:
                result["key"] = self._editing_key

            self.result = result
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e), parent=self)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AstroAlertApp().mainloop()
