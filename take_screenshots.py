#!/usr/bin/env python3
"""Launch the GUI, navigate each tab, capture screenshots, then quit."""

import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gui

OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

# Tab order: Dashboard(0), Sites(1), Schedule(2), Forecast(3), Chart(4), Scoring(5), Settings(6)
TABS = [
    (0, "dashboard.png"),
    (1, "sites.png"),
    (2, "schedule.png"),
    (3, "forecast.png"),
    (4, "chart.png"),
    (5, "scoring.png"),
    (6, "settings.png"),
]


def screencap(filename: str, win: tk.BaseWidget):
    win.update_idletasks()
    win.update()
    x = win.winfo_rootx()
    y = win.winfo_rooty()
    w = win.winfo_width()
    h = win.winfo_height()
    path = str(OUT / filename)
    subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path], check=True)
    print(f"  saved {filename}")


def run():
    app = gui.AstroAlertApp()
    app.lift()
    app.focus_force()

    def shoot(idx=0):
        if idx >= len(TABS):
            # Also capture the Add Site dialog
            dlg = gui.SiteDialog(app, title="Add Site")
            app.after(500, lambda: _snap_dialog(dlg))
            return
        tab_idx, filename = TABS[idx]
        app._nb.select(tab_idx)
        app.update_idletasks()
        app.update()
        app.after(500, lambda: _snap_tab(idx, filename))

    def _snap_tab(idx, filename):
        screencap(filename, app)
        shoot(idx + 1)

    def _snap_dialog(dlg):
        screencap("add_site_dialog.png", dlg)
        dlg.destroy()
        app.after(200, app.destroy)

    app.after(1400, shoot)
    app.mainloop()
    print("Done.")


if __name__ == "__main__":
    run()
