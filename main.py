"""Entry point for the AstroAlert app bundle.

When launched with CLI arguments, delegates to astro_alert.py (CLI mode).
When launched bare (double-click / no args), opens the GUI.
"""

import sys


def main() -> None:
    if sys.argv[1:]:
        import astro_alert
        astro_alert.main()
    else:
        from gui import AstroAlertApp
        app = AstroAlertApp()
        app.mainloop()


if __name__ == "__main__":
    main()
