# Astro Alert

Go/no-go email alert system for astrophotography sessions. Fetches weather, atmospheric seeing, and moon data for multiple sites near Durham, NC and sends a nightly summary to your inbox.

## Hardware

- **Camera:** ZWO ASI2600MC-Air (one-shot color)
- **Refractor:** Askar 120 APO + 0.8× reducer — 672mm f/5.6 (~2.0° × 1.34° FOV)
- **Mount:** ZWO AM5N

## How it works

Every evening at **6pm**, an email arrives with tomorrow night's forecast across all configured sites — so you have time to plan a dark site trip. At **2pm**, a second check runs for tonight; that email only sends if at least one site scores GO.

Each site is scored 0–100:

| Component | Weight | Source |
|-----------|--------|--------|
| Weather (clouds, precip, wind, dew) | 0–40 | Open-Meteo |
| Seeing & transparency | 0–30 | 7timer.info (ASTRO product) |
| Moon phase & position | 0–30 | ephem |

**GO threshold: 55/100.** Scoring is Bortle-aware — cloud cover is weighted more heavily at dark sites (Bortle ≤ 4) where sky quality is the whole point of the drive.

**Moon hard cutoff:** if the moon is ≥ 75% illuminated and still up at midnight, the night is automatically NO-GO regardless of score. If the moon is ≥ 75% but sets before midnight, the score reflects the usable dark hours after moonset (up to 12/30) and the email notes what time to start imaging.

## Sites

| Key | Name | Bortle | Drive |
|-----|------|--------|-------|
| `jordan_lake` | Jordan Lake SRA | 5 | 36 min |
| `eno_river` | Eno River State Park | 5 | 40 min |
| `little_river` | Little River Regional Park | 4 | 48 min |
| `medoc_mountain` | Medoc Mountain State Park | 4 | 70 min |
| `uwharrie` | Uwharrie National Forest | 3 | 105 min |
| `bladen_lakes` | Bladen Lakes State Forest | 3 | 120 min |
| `james_river` | James River State Park | 2 | 120 min |
| `staunton_river` | Staunton River State Park | 2 | 120 min |
| `durham_home` | Durham Home | 7 | — |

Site coordinates and metadata live in `sites.json`. Never hardcode coordinates — always read from that file.

## Setup

### 1. Install dependencies

```bash
pip install requests ephem twilio python-dotenv
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your credentials. Never commit `.env`.

```
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Google App Password (not your login password)
ALERT_EMAIL_TO=you@gmail.com
```

To create a Gmail App Password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2-Step Verification).

### 3. Install cron jobs

```bash
# 6pm daily — tomorrow night's forecast (always sends)
0 18 * * * /path/to/python3 /Users/pauldavis/astro_alert/astro_alert.py --tomorrow

# 2pm daily — tonight's conditions (only sends if a site is GO)
0 14 * * * /path/to/python3 /Users/pauldavis/astro_alert/astro_alert.py --only-if-go
```

Both jobs append to `astro_alert.log`.

## Usage

```bash
# Forecast all sites for tonight (dry run — no email)
python3 astro_alert.py --dry-run

# Forecast all sites for tomorrow night and send email
python3 astro_alert.py --tomorrow

# Check a single site
python3 astro_alert.py --site medoc_mountain --dry-run

# Only email if something is GO
python3 astro_alert.py --only-if-go

# List all configured sites
python3 astro_alert.py list-sites

# Add a new site
python3 astro_alert.py add-site my_spot "My Dark Spot" 35.5 -79.2 150 3 America/New_York

# Add a site and make it the default
python3 astro_alert.py add-site my_spot "My Dark Spot" 35.5 -79.2 150 3 America/New_York --set-active
```

## Email format

**Subject:** `Astro Alert tomorrow night — GO: Bladen Lakes State Forest (57/100)`

```
Moon: 79% illuminated  rises 20:22Z  sets 08:17Z

Jordan Lake SRA (36min drive)
  NO-GO — 30/100  [weather 8/40, seeing 21/30, moon 1/30]
  Partly cloudy (40% avg) · Poor transparency (2.3/8) · Bright moon (79% illuminated) · Moon up at midnight

Eno River State Park (40min drive)
  NO-GO — 29/100  [weather 8/40, seeing 20/30, moon 1/30]
  Partly cloudy (39% avg) · Poor transparency (2.0/8) · Bright moon (79% illuminated) · Moon up at midnight

Little River Regional Park (48min drive)
  NO-GO — 20/100  [weather 0/40, seeing 19/30, moon 1/30]
  Mostly cloudy (53% avg) · Poor transparency (2.0/8) · Bright moon (79% illuminated) · Moon up at midnight

Medoc Mountain State Park (70min drive)
  NO-GO — 50/100  [weather 30/40, seeing 19/30, moon 1/30]
  Poor transparency (2.3/8) · Bright moon (79% illuminated) · Moon up at midnight

Uwharrie National Forest (105min drive)
  NO-GO — 20/100  [weather 0/40, seeing 19/30, moon 1/30]
  Mostly cloudy (61% avg) · Poor transparency (2.0/8) · Bright moon (79% illuminated) · Moon up at midnight

Bladen Lakes State Forest (120min drive)
  GO — 57/100  [weather 22/40, seeing 34/30, moon 1/30]
  Poor transparency (2.3/8) · Bright moon (79% illuminated) · Moon up at midnight

James River State Park (120min drive)
  NO-GO — 20/100  [weather 0/40, seeing 19/30, moon 1/30]
  Mostly cloudy (73% avg) · Poor transparency (2.0/8) · Bright moon (79% illuminated) · Moon up at midnight

Staunton River State Park (120min drive)
  NO-GO — 33/100  [weather 12/40, seeing 20/30, moon 1/30]
  Partly cloudy (47% avg) · Poor transparency (2.3/8) · Bright moon (79% illuminated) · Moon up at midnight

Durham Home (home)
  NO-GO — 29/100  [weather 8/40, seeing 20/30, moon 1/30]
  Partly cloudy (32% avg) · Poor transparency (2.0/8) · Bright moon (79% illuminated) · Moon up at midnight
```

Sites are listed in drive-time order (shortest first). The subject line calls out the best GO site, or the highest-scoring site if everything is NO-GO.

## Project structure

```
astro_alert/
├── astro_alert.py       # CLI entry point
├── site_manager.py      # Load/save sites.json
├── weather.py           # Open-Meteo weather fetch
├── seeing.py            # 7timer.info seeing/transparency fetch
├── moon.py              # Moon phase and rise/set via ephem
├── scorer.py            # Bortle-aware 0–100 scoring
├── gmail_notifier.py    # Gmail SMTP email sender
├── notifier.py          # Alert dispatch (email; SMS pending registration)
├── sites.json           # Site database
├── .env                 # Credentials (never commit)
├── .env.example         # Credential template
└── test_*.py            # pytest test suite
```

## Running tests

```bash
python3 -m pytest test_*.py -v
```
