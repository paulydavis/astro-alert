# SMTP Provider-Neutral Support

**Date:** 2026-04-26
**Status:** Approved

## Problem

Astro Alert currently hardcodes Gmail SMTP settings (`smtp.gmail.com:587`) and uses Gmail-specific env var names (`GMAIL_USER`, `GMAIL_APP_PASSWORD`). Users on Outlook, Yahoo, or other providers cannot use the app.

## Goal

Default to Gmail (no change for existing users), but allow any SMTP provider via an optional "Use a different email provider" toggle in the GUI Settings tab and configurable env vars.

---

## Section 1: Config / Env Vars

New env vars:

| Var | Default | Description |
|-----|---------|-------------|
| `SMTP_USER` | — | Sending email address (replaces `GMAIL_USER`) |
| `SMTP_PASSWORD` | — | App password or SMTP password (replaces `GMAIL_APP_PASSWORD`) |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `ALERT_EMAIL_TO` | *(unchanged)* | Recipient address |

**Backwards compatibility:** the config loader checks `SMTP_USER` first, falls back to `GMAIL_USER` if absent. Same for `SMTP_PASSWORD` / `GMAIL_APP_PASSWORD`. Existing `.env` files require no changes.

---

## Section 2: Code Changes

- Rename `gmail_notifier.py` → `smtp_notifier.py`
- Replace hardcoded `SMTP_HOST`/`SMTP_PORT` constants with env-read values (defaulting to Gmail settings)
- Replace `GMAIL_USER`/`GMAIL_APP_PASSWORD` env reads with `SMTP_USER`/`SMTP_PASSWORD` + fallback
- Remove Gmail-specific language from error messages (e.g. "Auth failed — check your App Password" not "Gmail auth failed")
- Update all imports: `astro_alert.py`, `notifier.py`, `gui.py`, all `test_*.py` files
- `SiteReport`, `EmailResult`, `send_multi_site_alert`, `send_test_email` signatures unchanged

---

## Section 3: GUI — Settings Tab

- Rename field label "Gmail address" → "Email address"
- "App Password" label unchanged
- Add checkbox below existing fields: **"Use a different email provider (custom SMTP)"**
  - Unchecked by default; hides SMTP host/port fields
  - When checked: reveals two fields:
    - **SMTP host** — text input, pre-filled with `smtp.gmail.com`
    - **SMTP port** — numeric input, pre-filled with `587`
- Save Credentials writes all four values (`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`) to env file
- On load: checkbox auto-ticks if `SMTP_HOST` is set and differs from `smtp.gmail.com`
- "Send test email" button unchanged

---

## Section 4: README / Docs

- Update credentials env var table: `SMTP_USER`, `SMTP_PASSWORD`, add optional `SMTP_HOST`, `SMTP_PORT`
- Add short note: Gmail is the default; any SMTP provider works with custom host/port
- Add provider reference table:

| Provider | SMTP Host | Port |
|----------|-----------|------|
| Gmail | smtp.gmail.com | 587 |
| Outlook / Hotmail | smtp-mail.outlook.com | 587 |
| Yahoo Mail | smtp.mail.yahoo.com | 587 |
| iCloud Mail | smtp.mail.me.com | 587 |

- Rename section heading "Creating a Gmail App Password" → "Gmail users: create an App Password" to clarify it's Gmail-specific
- Update Settings tab screenshot once GUI changes are complete

---

## Out of Scope

- OAuth / token-based auth
- Multiple sending accounts
- SSL-only (port 465) — all common providers support STARTTLS on 587
