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


def screencap(filename: str, app: tk.Tk):
    app.update_idletasks()
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    w = app.winfo_width()
    h = app.winfo_height()
    path = str(OUT / filename)
    subprocess.run([
        "screencapture", "-x", "-R", f"{x},{y},{w},{h}", path
    ])
    print(f"  saved {path}")


def run():
    app = gui.AstroAlertApp()
    app.lift()
    app.focus_force()

    def step1():
        # Dashboard — run a dry-run first so there's output
        app._night_var.set("tonight")
        app._dry_run_var.set(True)
        app._start_forecast()
        _wait_for_forecast(step2)

    def _wait_for_forecast(callback, max_ms=30000, interval=500):
        if str(app._run_btn.cget("state")) != "disabled":
            app.after(300, callback)  # small extra pause so output renders
        elif max_ms <= 0:
            app.after(0, callback)
        else:
            app.after(interval, lambda: _wait_for_forecast(callback, max_ms - interval, interval))

    def step2():
        screencap("dashboard.png", app)
        # Switch to Sites tab
        app._nb.select(1)
        app.after(500, step3)

    def step3():
        screencap("sites.png", app)
        # Switch to Schedule tab
        app._nb.select(2)
        app.after(600, step4)

    def step4():
        screencap("schedule.png", app)
        # Open Add Site dialog
        dlg = gui.SiteDialog(app, title="Add Site")
        app.after(400, lambda: step5(dlg))

    def step5(dlg):
        screencap("add_site.png", app)  # capture main window with dialog on top
        # Also capture just the dialog
        dlg.update_idletasks()
        x = dlg.winfo_rootx()
        y = dlg.winfo_rooty()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        path = str(OUT / "add_site_dialog.png")
        subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path])
        print(f"  saved {path}")
        dlg.destroy()
        app.after(300, app.destroy)

    app.after(1500, step1)
    app.mainloop()
    print("Screenshots done.")


if __name__ == "__main__":
    run()
