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
        self._tab_settings = ttk.Frame(nb)

        nb.add(self._tab_dash,     text="  Dashboard  ")
        nb.add(self._tab_sites,    text="  Sites  ")
        nb.add(self._tab_sched,    text="  Schedule  ")
        nb.add(self._tab_settings, text="  Settings  ")

        self._build_dashboard(self._tab_dash)
        self._build_sites_tab(self._tab_sites)
        self._build_schedule_tab(self._tab_sched)
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
        cols = ("key", "name", "bortle", "drive", "timezone", "active")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings",
                                   selectmode="browse")

        for cid, heading, width, anchor in [
            ("key",      "Key",       120, "w"),
            ("name",     "Name",      200, "w"),
            ("bortle",   "Bortle",     70, "center"),
            ("drive",    "Drive",      80, "center"),
            ("timezone", "Timezone",  180, "w"),
            ("active",   "Active",     60, "center"),
        ]:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=width, minwidth=50, anchor=anchor)

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(26, 0), pady=22)
        vsb.pack(side="left", fill="y", pady=22)

        btns = ttk.Frame(parent)
        btns.pack(side="right", fill="y", padx=22, pady=22)

        ttk.Button(btns, text="Add Site",
                   command=self._add_site_dialog).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Edit Site",
                   command=self._edit_site_dialog).pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Set Active", style="Accent.TButton",
                   command=self._set_active_site).pack(fill="x", pady=(0, 8))
        ttk.Separator(btns).pack(fill="x", pady=8)
        ttk.Button(btns, text="Delete Site", style="Danger.TButton",
                   command=self._delete_site).pack(fill="x")

    def _refresh_sites(self):
        if hasattr(self, "_tree"):
            for row in self._tree.get_children():
                self._tree.delete(row)
            try:
                entries = list_sites()
            except FileNotFoundError:
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
            "lat":         str(getattr(site, "lat",     "")) if site else "",
            "lon":         str(getattr(site, "lon",     "")) if site else "",
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
