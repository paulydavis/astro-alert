#!/usr/bin/env python3
"""Astro Alert — GUI configuration and control panel."""

import io
import platform
import sys
import threading
import tkinter as tk
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
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self._tab_dash  = ttk.Frame(nb)
        self._tab_sites = ttk.Frame(nb)
        self._tab_sched = ttk.Frame(nb)

        nb.add(self._tab_dash,  text="  Dashboard  ")
        nb.add(self._tab_sites, text="  Sites  ")
        nb.add(self._tab_sched, text="  Schedule  ")

        self._build_dashboard(self._tab_dash)
        self._build_sites_tab(self._tab_sites)
        self._build_schedule_tab(self._tab_sched)

    # ── Dashboard ───────────────────────────────────────────────────────────────

    def _build_dashboard(self, parent):
        # Controls row
        ctrl = ttk.Frame(parent)
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
        inner.place(relx=0.5, rely=0.46, anchor="center")

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
        ("key",          "Key",              str,   True),
        ("name",         "Name",             str,   True),
        ("lat",          "Latitude",         float, True),
        ("lon",          "Longitude",        float, True),
        ("elevation_m",  "Elevation (m)",    float, True),
        ("bortle",       "Bortle  (1 – 9)",  int,   True),
        ("timezone",     "Timezone (IANA)",  str,   True),
        ("drive_min",    "Drive (min)",      int,   False),
        ("notes",        "Notes",            str,   False),
    ]

    def __init__(self, parent, title="Site", site=None, key=None):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.geometry("500x570")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._editing_key = key   # None when adding, set when editing
        self._build(site, key)

    def _build(self, site, key):
        ttk.Label(self, text=self.title(),
                  font=(FONT_PROP, 15, "bold")).pack(pady=(22, 0))
        ttk.Separator(self).pack(fill="x", padx=30, pady=14)

        grid = ttk.Frame(self)
        grid.pack(padx=36, fill="x")
        grid.columnconfigure(1, weight=1)

        defaults = {
            "key":         key            or "",
            "name":        getattr(site, "name",        "") or "",
            "lat":         str(getattr(site, "lat",     "")) if site else "",
            "lon":         str(getattr(site, "lon",     "")) if site else "",
            "elevation_m": str(getattr(site, "elevation_m", "")) if site else "",
            "bortle":      str(getattr(site, "bortle",  "")) if site else "",
            "timezone":    getattr(site, "timezone",    "America/New_York") or "America/New_York",
            "drive_min":   str(site.drive_min) if (site and site.drive_min) else "",
            "notes":       getattr(site, "notes", "")  or "",
        }

        self._vars: dict[str, tk.StringVar] = {}
        for row_idx, (field, label, _, _req) in enumerate(self._FIELDS):
            ttk.Label(grid, text=label + ":", style="Dim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=6, padx=(0, 8))
            var   = tk.StringVar(value=defaults[field])
            state = "disabled" if (field == "key" and key) else "normal"
            ttk.Entry(grid, textvariable=var, font=(FONT_PROP, 12),
                      state=state).grid(row=row_idx, column=1, sticky="ew", pady=6)
            self._vars[field] = var

        self._set_active_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Set as active site",
                         variable=self._set_active_var).pack(pady=(12, 0))

        ttk.Separator(self).pack(fill="x", padx=30, pady=14)

        btns = ttk.Frame(self)
        btns.pack(pady=(0, 22))
        ttk.Button(btns, text="Cancel",
                   command=self.destroy).pack(side="left", padx=(0, 14))
        ttk.Button(btns, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="left")

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

            # When editing, key field is disabled — restore the original key
            if self._editing_key:
                result["key"] = self._editing_key

            self.result = result
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e), parent=self)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AstroAlertApp().mainloop()
