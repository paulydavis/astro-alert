#!/usr/bin/env python3
"""Astro Alert — astrophotography go/no-go SMS alert system."""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from smtp_notifier import SiteReport, send_multi_site_alert
from moon import get_moon_info
from scorer import score_night
from scoring_weights import load_weights
from seeing import fetch_seeing
from site_manager import add_site, get_active_site, list_sites, equipment_string
from weather import fetch_weather


def cmd_list_sites(_args) -> None:
    entries = list_sites()
    if not entries:
        print("No sites configured.")
        return
    for key, site, is_active in entries:
        marker = "* " if is_active else "  "
        drive = f"{site.drive_min}min" if site.drive_min else "home"
        notes = f"  [{site.notes}]" if site.notes else ""
        print(f"{marker}{key}: {site.name}  Bortle {site.bortle}  {drive}{notes}")


def cmd_add_site(args) -> None:
    site = add_site(
        key=args.key,
        name=args.name,
        lat=args.lat,
        lon=args.lon,
        elevation_m=args.elevation,
        bortle=args.bortle,
        timezone=args.timezone,
        set_active=args.set_active,
    )
    action = "Added and activated" if args.set_active else "Added"
    print(f"{action} site {site.key!r}: {site.name}")


def _fetch_report(site, target_date) -> SiteReport:
    weights = load_weights()
    weather = fetch_weather(site.key, site.lat, site.lon, target_date=target_date)
    seeing = fetch_seeing(site.key, site.lat, site.lon)
    moon = get_moon_info(site.lat, site.lon, target_date=target_date)
    score = score_night(weather, seeing, moon, bortle=site.bortle, target_date=target_date, weights=weights)
    return SiteReport(site_name=site.name, drive_min=site.drive_min, score=score, moon=moon)


def _generate_cards(site_report_pairs: list, target_date, openai_key: str) -> dict:
    """Generate report card PNGs for GO sites. Returns {site_name: Path}."""
    from data_dir import DATA_DIR
    from moon import compute_imaging_window
    from target_recommender import get_nightly_targets
    from card_generator import CardInput, generate_site_card

    output_dir = DATA_DIR / "report_cards"
    cards = {}
    go_pairs = [(s, r) for s, r in site_report_pairs if r.score.go]
    if not go_pairs:
        return cards

    print(f"Generating report cards for {len(go_pairs)} GO site(s)…")
    for site, report in go_pairs:
        print(f"  {site.name}…", end=" ", flush=True)
        try:
            window = compute_imaging_window(site.lat, site.lon, target_date)
            targets = get_nightly_targets(site.lat, site.lon, window, max_results=12) if window else []
            card = CardInput(
                site_name=site.name,
                site_key=site.key,
                site_bortle=site.bortle,
                site_tz=getattr(site, "timezone", "UTC"),
                target_date=target_date,
                score=report.score,
                moon=report.moon,
                targets=targets,
                drive_min=site.drive_min,
                equipment=equipment_string(),
            )
            png_path, _ = generate_site_card(card, openai_key, output_dir)
            if png_path:
                cards[site.name] = png_path
                print("done")
            else:
                print("failed (card render error)")
        except Exception as exc:
            print(f"failed ({exc})")
    return cards


def cmd_run(args) -> None:
    now_utc = datetime.now(timezone.utc)
    # Noon UTC ≈ 8 AM Eastern — anything before that is still "last night" locally.
    today = now_utc.date() if now_utc.hour >= 12 else (now_utc - timedelta(days=1)).date()
    target_date = today + timedelta(days=1) if args.tomorrow else today
    night_label = "tomorrow night" if args.tomorrow else "tonight"

    if args.site:
        try:
            site = get_active_site(override=args.site)
        except (KeyError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        sites_to_fetch = [site]
    else:
        entries = list_sites()
        sites_to_fetch = sorted(
            [s for _, s, _ in entries],
            key=lambda s: (s.drive_min is None, s.drive_min or 0),
        )

    print(f"Fetching conditions for {len(sites_to_fetch)} site(s) — {night_label} ({target_date})…")
    reports = []
    for site in sites_to_fetch:
        print(f"  {site.name}…", end=" ", flush=True)
        report = _fetch_report(site, target_date)
        go_label = "GO" if report.score.go else "no-go"
        print(f"{go_label} ({report.score.total}/100)")
        reports.append(report)

    # Print summary
    moon = reports[0].moon
    print(f"\nMoon: {moon.phase_pct:.0f}% illuminated", end="")
    if moon.rise_utc:
        print(f"  rises {moon.rise_utc.strftime('%H:%MZ')}", end="")
    if moon.set_utc:
        print(f"  sets {moon.set_utc.strftime('%H:%MZ')}", end="")
    print("\n")
    for r in reports:
        go_label = "GO    " if r.score.go else "NO-GO "
        drive = f"{r.drive_min}min" if r.drive_min else "home "
        print(f"  {go_label} {r.score.total:3}/100  {drive:7}  {r.site_name}")
        if r.score.warnings:
            print("         " + " · ".join(r.score.warnings))
    print()

    any_go = any(r.score.go for r in reports)
    if args.only_if_go and not any_go:
        print("No sites are GO — skipping email (--only-if-go).")
        return

    if args.dry_run:
        print("(dry-run: email not sent)")
        return

    # Generate report cards for GO sites when sending HTML email
    import os
    from dotenv import load_dotenv
    from data_dir import ENV_FILE
    load_dotenv(ENV_FILE, override=True)
    card_pngs = {}
    if os.getenv("EMAIL_FORMAT", "plain") == "html" and any_go:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        site_report_pairs = list(zip(sites_to_fetch, reports))
        card_pngs = _generate_cards(site_report_pairs, target_date, openai_key)

    result = send_multi_site_alert(reports, night_label=night_label,
                                    sites=sites_to_fetch,
                                    card_pngs=card_pngs or None)
    if result.sent:
        cards_note = f" with {len(card_pngs)} card(s)" if card_pngs else ""
        print(f"Alert sent via EMAIL{cards_note}")
    else:
        print(f"Alert failed: {result.error}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astro_alert",
        description="Astrophotography go/no-go alert system.",
    )
    parser.add_argument(
        "--site",
        metavar="KEY",
        help="Fetch a single site instead of all sites.",
    )
    parser.add_argument(
        "--tomorrow",
        action="store_true",
        help="Forecast tomorrow night instead of tonight (use for 6pm planning alert).",
    )
    parser.add_argument(
        "--only-if-go",
        action="store_true",
        help="Suppress email if no sites score GO (use for same-day nudge).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score conditions but do not send email.",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list-sites", help="List all configured sites.")

    add = sub.add_parser("add-site", help="Add or update a site.")
    add.add_argument("key", help="Short identifier, e.g. 'medoc'.")
    add.add_argument("name", help="Human-readable name.")
    add.add_argument("lat", type=float, help="Latitude (decimal degrees).")
    add.add_argument("lon", type=float, help="Longitude (decimal degrees).")
    add.add_argument("elevation", type=float, help="Elevation in metres.")
    add.add_argument("bortle", type=int, choices=range(1, 10), metavar="BORTLE",
                     help="Bortle scale 1–9.")
    add.add_argument("timezone", help="IANA timezone, e.g. 'America/New_York'.")
    add.add_argument("--set-active", action="store_true",
                     help="Make this site the default active site.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-sites":
        cmd_list_sites(args)
    elif args.command == "add-site":
        try:
            cmd_add_site(args)
        except (KeyError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
