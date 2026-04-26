# Astro Alert

Go/no-go email alert system for astrophotography sessions. Fetches weather, atmospheric seeing, and moon data for your dark-sky sites, scores each one 0–100, and sends a nightly summary to your inbox — so you know whether it's worth heading out before it gets dark.

## GUI

Astro Alert has a graphical control panel with four tabs:

**Dashboard** — run a dry-run or live forecast for any site, with colour-coded GO/NO-GO output.

![Dashboard](screenshots/dashboard.png)

**Sites** — add, edit, delete, and activate sites. The Add Site dialog geocodes a place name to fill coordinates automatically, fetches elevation from Open-Meteo, and links to lightpollutionmap.info for Bortle lookup.

![Sites](screenshots/sites.png)

![Add Site dialog](screenshots/add_site_dialog.png)

**Schedule** — set up the two automatic daily emails with one click. Astro Alert runs itself in the background every day — no need to remember to open it.

![Schedule](screenshots/schedule.png)

**Settings** — enter your Gmail address and App Password. Also set your **Home Location** (address search with autocomplete) — this becomes the starting point for automatic drive-time calculations. Credentials and home location are saved to your OS user data directory (never next to the source files).

![Settings](screenshots/settings.png)

## Installation (no Python required)

Download the latest release for your platform from the [Releases page](https://github.com/paulydavis/astro-alert/releases), or build it yourself from source (see below). No Python installation needed.

### Building from source

#### macOS → `AstroAlert.app`

```bash
bash build.sh
# Output: dist/AstroAlert.app
cp -r dist/AstroAlert.app /Applications/
```

Double-click **AstroAlert** in your Applications folder. On first launch macOS Gatekeeper will block it because it isn't signed. Right-click the app → **Open** → **Open** to allow it once. After that it opens normally.

#### Windows → `AstroAlert.exe`

Double-click **`build.bat`** (or run it from a command prompt that has Python on its PATH).

```
Output: dist\AstroAlert.exe
```

Copy `AstroAlert.exe` anywhere you like and double-click it. Windows SmartScreen will warn about an unsigned app — click **More info** → **Run anyway** to proceed.

#### Linux → `AstroAlert` binary

```bash
bash build.sh
# Output: dist/AstroAlert
chmod +x dist/AstroAlert
./dist/AstroAlert
```

To add it to your application menu, copy the binary to a permanent location and edit `AstroAlert.desktop` to point `Exec=` at it, then install with:

```bash
cp AstroAlert.desktop ~/.local/share/applications/
```

#### Code signing (optional — removes OS warnings)

Both Gatekeeper and SmartScreen warnings go away when the app is signed by a trusted certificate authority.

| Platform | Option | Cost | Notes |
|---|---|---|---|
| Windows | **Azure Trusted Signing** | ~$10/month | Microsoft's own CA; establishes SmartScreen reputation immediately; no hardware token |
| Windows | EV certificate | ~$300–500/year | DigiCert, Sectigo, GlobalSign; ships a USB hardware token for local signing |
| macOS | Apple Developer Program | $99/year | Required for Gatekeeper notarisation; sign with `codesign`, notarise with `xcrun notarytool` |

For a personal or open-source project distributed via GitHub Releases, the unsigned warnings are normal and most users expect them. The "right-click → Open" / "More info → Run anyway" workarounds are one-time steps.

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

These are the author's sites near Durham, NC. See [Setup](#setup) to replace them with your own. Site coordinates and metadata live in `sites.json`; use `sites.example.json` as a starting template.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/paulydavis/astro-alert.git
cd astro-alert
pip install -r requirements.txt
```

**Python 3.11 or newer is required.**

- **Windows:** download from [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"** during install. tkinter is included. Use `python` instead of `python3` in all commands below.
- **macOS:** tkinter is included with the python.org installer. If you use Homebrew Python, run `brew install python-tk` too.
- **Linux:** install tkinter via your package manager if it isn't already present:

```bash
# Debian/Ubuntu
sudo apt install python3-tk

# Fedora/RHEL
sudo dnf install python3-tkinter
```

### 2. Configure credentials

**Option A — GUI (easiest):** open the app. If no credentials are configured, it opens directly on the **Settings** tab. Enter your Gmail address and App Password and click **Save Credentials**. While you're there, set your **Home Location** — search your address and click **Save Home Location** so drive times calculate automatically when you add sites.

**Option B — manually:** copy `.env.example` to `.env` (in the same directory as the source) and fill in your details. Never commit `.env`.

```
SMTP_USER=you@example.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # App Password or provider equivalent (not your login password)
ALERT_EMAIL_TO=you@example.com      # optional — defaults to SMTP_USER
# Optional — only needed for non-Gmail providers:
SMTP_HOST=smtp.gmail.com            # defaults to smtp.gmail.com
SMTP_PORT=587                       # defaults to 587
```

Gmail is the default. To use another provider, set `SMTP_HOST` and `SMTP_PORT` (or use the custom SMTP toggle in the Settings tab):

| Provider | SMTP Host | Port |
|----------|-----------|------|
| Gmail | smtp.gmail.com | 587 |
| Outlook / Hotmail | smtp-mail.outlook.com | 587 |
| Yahoo Mail | smtp.mail.yahoo.com | 587 |
| iCloud Mail | smtp.mail.me.com | 587 |

When running from a packaged app, credentials are saved to your OS user data directory instead:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/AstroAlert/.env` |
| Windows | `%APPDATA%\AstroAlert\.env` |
| Linux | `~/.config/AstroAlert/.env` |

#### Gmail users: create an App Password

Astro Alert uses Gmail's SMTP service to send email. It needs an **App Password** — a 16-character code that works in place of your real password. Your normal Gmail password will not work here.

**Prerequisites:** 2-Step Verification must be enabled on your Google account. If it isn't, [enable it first](https://myaccount.google.com/signinoptions/twosv).

**Steps:**

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (sign in if prompted)
2. Under "App name", type something like `Astro Alert`
3. Click **Create**
4. Google shows a 16-character password like `zubn qqeh qqyj ywnt` — copy it now (it won't be shown again)
5. Paste it into the **App password** field in the Settings tab (spaces are fine — Gmail accepts them)

> **Note:** If you don't see the App Passwords page, your account may be managed by Google Workspace (a school or company). In that case an admin needs to allow less-secure app access, or you need to use a personal Gmail account.

### 3. Set up your sites

The included `sites.json` is pre-loaded with dark sites near Durham, NC. To use your own locations, replace it with the template:

```bash
cp sites.example.json sites.json
```

**Option A — GUI (easiest):** open the app, go to the **Sites** tab, and click **Add Site**. Type a place name to geocode coordinates and elevation automatically. Click **Calculate ↗** next to the Drive field to get a real driving time from your home (requires Home Location to be set in Settings first).

**Option B — CLI:**

```bash
# Add your backyard
python3 astro_alert.py add-site home "My Backyard" 40.7128 -74.0060 10 7 America/New_York --set-active

# Add a dark site
python3 astro_alert.py add-site dark "Cherry Springs SP" 41.6629 -77.8236 670 2 America/New_York

# Confirm your sites
python3 astro_alert.py list-sites
```

Find your Bortle class at [lightpollutionmap.info](https://www.lightpollutionmap.info) and your IANA timezone at [en.wikipedia.org/wiki/List_of_tz_database_time_zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

### 4. Set up automatic daily emails

A **cron job** (macOS/Linux) or **Scheduled Task** (Windows) is like a built-in alarm clock for your computer — except instead of waking you up, it quietly runs a program in the background at a set time every day, without you opening anything or remembering to do it. Once it's set up, it just works. Astro Alert uses two of these — one at 6pm for tomorrow's forecast, one at 2pm for a same-day nudge — so your inbox gets the forecast automatically.

**Option A — GUI (easiest):** open the app, go to the **Schedule** tab, and click **Install Schedule**. Done.

**Option B — manual:** edit your crontab (`crontab -e`) and add these two lines (replace `/path/to/python3` and `/path/to/astro-alert`):

```
# 6pm daily — tomorrow night's forecast (always sends)
0 18 * * * /path/to/python3 /path/to/astro-alert/astro_alert.py --tomorrow >> /path/to/astro-alert/astro_alert.log 2>&1

# 2pm daily — tonight's conditions (only sends if a site is GO)
0 14 * * * /path/to/python3 /path/to/astro-alert/astro_alert.py --only-if-go >> /path/to/astro-alert/astro_alert.log 2>&1
```

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
├── main.py              # Entry point: GUI when run bare, CLI when run with args
├── astro_alert.py       # CLI entry point and argument parser
├── gui.py               # Tkinter GUI (dashboard, sites, schedule, settings)
├── data_dir.py          # Platform-aware user data directory
├── scheduler_setup.py   # Cross-platform cron / Task Scheduler install
├── site_manager.py      # Load/save sites.json
├── weather.py           # Open-Meteo weather fetch
├── seeing.py            # 7timer.info seeing/transparency fetch
├── moon.py              # Moon phase and rise/set via ephem
├── scorer.py            # Bortle-aware 0–100 scoring
├── gmail_notifier.py    # Gmail SMTP email sender
├── notifier.py          # Alert dispatch
├── sites.json           # Site database (your locations)
├── sites.example.json   # Starter template
├── .env                 # Credentials for dev use (never commit)
├── .env.example         # Credential template
├── AstroAlert.spec      # PyInstaller build spec (cross-platform)
├── build.sh             # Build script for macOS / Linux
├── build.bat            # Build script for Windows
├── AstroAlert.desktop   # Linux app menu entry template
└── test_*.py            # pytest test suite (274 tests)
```

## Running tests

```bash
python3 -m pytest test_*.py -v
```
