"""Send go/no-go alerts via Gmail SMTP."""

import os
import smtplib
import unicodedata
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv

from moon import MoonInfo
from scorer import Score

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


@dataclass
class SiteReport:
    site_name: str
    drive_min: Optional[int]
    score: Score
    moon: MoonInfo


@dataclass
class EmailResult:
    sent: bool
    error: Optional[str] = None


def _clean(s: Optional[str]) -> str:
    """Normalize and strip a credential string, removing invisible Unicode."""
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip()


def _format_report(report: SiteReport) -> list[str]:
    score = report.score
    moon = report.moon
    go_label = "GO" if score.go else "NO-GO"
    drive = f"{report.drive_min}min drive" if report.drive_min else "home"
    lines = [
        f"{report.site_name} ({drive})",
        f"  {go_label} - {score.total}/100  "
        f"[weather {score.weather_score}/40, seeing {score.seeing_score}/30, moon {score.moon_score}/30]",
    ]
    if score.warnings:
        lines.append("  " + " / ".join(score.warnings))
    return lines


def send_multi_site_alert(reports: list[SiteReport], night_label: str = "tonight") -> EmailResult:
    """Send a single email summarising all sites. Returns EmailResult — never raises."""
    from data_dir import ENV_FILE
    load_dotenv(ENV_FILE, override=True)
    gmail_user         = _clean(os.getenv("GMAIL_USER"))
    gmail_app_password = _clean(os.getenv("GMAIL_APP_PASSWORD"))
    email_to           = _clean(os.getenv("ALERT_EMAIL_TO")) or gmail_user

    missing = [k for k, v in {
        "GMAIL_USER": gmail_user,
        "GMAIL_APP_PASSWORD": gmail_app_password,
    }.items() if not v]
    if missing:
        return EmailResult(sent=False, error=f"Missing env vars: {', '.join(missing)}")

    go_sites = [r for r in reports if r.score.go]
    best = go_sites[0] if go_sites else None

    if best:
        subject = f"Astro Alert {night_label} - GO: {best.site_name} ({best.score.total}/100)"
    else:
        top = max(reports, key=lambda r: r.score.total)
        subject = f"Astro Alert {night_label} - NO-GO (best: {top.site_name} {top.score.total}/100)"

    moon = reports[0].moon
    moon_line = f"Moon: {moon.phase_pct:.0f}% illuminated"
    if moon.rise_utc:
        moon_line += f"  rises {moon.rise_utc.strftime('%H:%MZ')}"
    if moon.set_utc:
        moon_line += f"  sets {moon.set_utc.strftime('%H:%MZ')}"

    body_lines = [moon_line, ""]
    for report in reports:
        body_lines.extend(_format_report(report))
        body_lines.append("")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.set_content("\n".join(body_lines).strip())

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg, from_addr=gmail_user, to_addrs=[email_to])
        return EmailResult(sent=True)
    except smtplib.SMTPAuthenticationError:
        return EmailResult(sent=False, error="Gmail auth failed - check GMAIL_APP_PASSWORD")
    except Exception as e:
        return EmailResult(sent=False, error=str(e))


def send_test_email() -> EmailResult:
    """Send a one-line test email to verify credentials. Returns EmailResult — never raises."""
    from data_dir import ENV_FILE
    load_dotenv(ENV_FILE, override=True)
    gmail_user         = _clean(os.getenv("GMAIL_USER"))
    gmail_app_password = _clean(os.getenv("GMAIL_APP_PASSWORD"))
    email_to           = _clean(os.getenv("ALERT_EMAIL_TO")) or gmail_user

    if not gmail_user or not gmail_app_password:
        return EmailResult(sent=False, error="Credentials not configured.")

    msg = EmailMessage()
    msg["Subject"] = "Astro Alert - Test Email"
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.set_content("Your Astro Alert credentials are working correctly!")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg, from_addr=gmail_user, to_addrs=[email_to])
        return EmailResult(sent=True)
    except smtplib.SMTPAuthenticationError:
        return EmailResult(sent=False, error="Gmail auth failed - check your App Password.")
    except Exception as e:
        return EmailResult(sent=False, error=str(e))
