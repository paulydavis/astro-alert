"""Send go/no-go alerts via SMTP (defaults to Gmail)."""

import html
import os
import smtplib
import unicodedata
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv

from moon import MoonInfo
from scorer import Score

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


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


def _validate_address(addr: str) -> Optional[str]:
    """Return an error string if addr doesn't look like a valid email, else None."""
    if not addr:
        return "Email address is empty."
    if "@" not in addr:
        return f"'{addr}' is missing @."
    local, _, domain = addr.partition("@")
    if not local:
        return f"'{addr}' has nothing before @."
    if "." not in domain or ".." in domain or domain.startswith(".") or domain.endswith("."):
        return f"'{addr}' has an invalid domain."
    return None


def _load_smtp_config() -> tuple[str, str, str, int]:
    """Read SMTP settings from env; SMTP_USER/SMTP_PASSWORD fall back to GMAIL_* vars."""
    user = _clean(os.getenv("SMTP_USER") or os.getenv("GMAIL_USER", ""))
    password = _clean(os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", ""))
    host = _clean(os.getenv("SMTP_HOST", "")) or DEFAULT_SMTP_HOST
    try:
        port = int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    except (ValueError, TypeError):
        port = DEFAULT_SMTP_PORT
    return user, password, host, port


def _format_report(report: SiteReport) -> list[str]:
    score = report.score
    moon = report.moon
    go_label = "GO" if score.go else "NO-GO"
    drive = f"{report.drive_min}min drive" if report.drive_min else "home"
    lines = [
        f"{report.site_name} ({drive})",
        f"  {go_label} - {score.total}/100  "
        f"[weather {score.weather_score}%, seeing {score.seeing_score}%, moon {score.moon_score}%]",
    ]
    if score.warnings:
        lines.append("  " + " / ".join(score.warnings))
    return lines


def _render_targets_html(targets: list) -> str:
    """Return an HTML table of target recommendations, or empty string if no targets."""
    if not targets:
        return ""
    th = (
        '<th style="text-align:left;padding:3px 10px 3px 0;'
        'color:#8b949e;font-weight:normal;white-space:nowrap">'
    )
    td = '<td style="padding:2px 10px 2px 0;white-space:nowrap">'
    td_desc = '<td style="padding:2px 0;color:#8b949e">'
    rows = "".join(
        f"<tr>"
        f"{td}{html.escape(t.name)}</td>"
        f"{td}{html.escape(t.common_name)}</td>"
        f"{td}{html.escape(t.type)}</td>"
        f"{td}{t.peak_alt_deg:.0f}°</td>"
        f"{td}{t.hours_visible:.0f}h</td>"
        f"{td}{t.transit_utc.strftime('%H:%M') if t.transit_utc else '—'} UTC</td>"
        f"{td_desc}{html.escape(t.description)}</td>"
        f"</tr>"
        for t in targets
    )
    return (
        '<h4 style="font-family:monospace;color:#58a6ff;margin:14px 0 6px">'
        "Recommended Targets</h4>"
        '<table style="border-collapse:collapse;font-family:monospace;'
        'font-size:11px;color:#c9d1d9">'
        f"<tr>{th}Name</th>{th}Common Name</th>{th}Type</th>"
        f"{th}Peak Alt</th>{th}Hrs Vis</th>{th}Transits (UTC)</th>"
        f'{th}Description</th></tr>'
        + rows
        + "</table>"
    )


def send_multi_site_alert(reports: list[SiteReport], night_label: str = "tonight",
                           sites: Optional[list] = None) -> EmailResult:
    """Send a single email summarising all sites. Returns EmailResult — never raises."""
    from data_dir import ENV_FILE
    load_dotenv(ENV_FILE, override=True)
    smtp_user, smtp_password, smtp_host, smtp_port = _load_smtp_config()
    email_to = _clean(os.getenv("ALERT_EMAIL_TO")) or smtp_user

    if not smtp_user:
        return EmailResult(sent=False, error="Missing env var: SMTP_USER")
    if not smtp_password:
        return EmailResult(sent=False, error="Missing env var: SMTP_PASSWORD")
    for addr in (smtp_user, email_to):
        err = _validate_address(addr)
        if err:
            return EmailResult(sent=False, error=f"Invalid address: {err}")

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

    email_format = _clean(os.getenv("EMAIL_FORMAT", "plain"))

    if email_format == "html" and sites:
        try:
            import logging as _logging
            from chart_html import build_chart_data, render_chart_fragment, render_legend_html
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            site_by_name = {s.name: s for s in sites}
            legend_html  = render_legend_html()

            moon_header = (
                f'<p style="font-family:monospace;color:#c9d1d9;margin:16px 0 8px">'
                f'{html.escape(moon_line)}</p>'
            )

            # Build one block per site: chart + legend + text summary
            blocks = []
            for report in reports:
                site_obj = site_by_name.get(report.site_name)
                text_lines = _format_report(report)
                text_block = (
                    f'<pre style="font-family:monospace;color:#c9d1d9;'
                    f'margin:4px 0 0">{html.escape(chr(10).join(text_lines))}</pre>'
                )

                if site_obj is not None:
                    try:
                        chart_data    = build_chart_data(site_obj, hours=72)
                        chart_html_frag = render_chart_fragment(chart_data)
                    except Exception as _chart_exc:
                        _logging.getLogger(__name__).warning(
                            "Chart build failed for %s: %s", report.site_name, _chart_exc
                        )
                        chart_html_frag = (
                            f'<p style="color:#e3b341;font-size:11px">'
                            f'⚠ Chart unavailable: {html.escape(str(_chart_exc))}</p>'
                        )
                else:
                    chart_html_frag = ""

                heading = (
                    f'<h3 style="font-family:monospace;color:#58a6ff;'
                    f'margin:24px 0 6px">{html.escape(report.site_name)}</h3>'
                )

                targets_html = ""
                if report.score.go and site_obj is not None:
                    try:
                        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                        from moon import compute_imaging_window
                        from target_recommender import get_nightly_targets
                        today_utc = _dt.now(_tz.utc).date()
                        target_date = (
                            today_utc + _td(days=1)
                            if "tomorrow" in night_label
                            else today_utc
                        )
                        window = compute_imaging_window(site_obj.lat, site_obj.lon, target_date)
                        site_targets = get_nightly_targets(site_obj.lat, site_obj.lon, window)
                        targets_html = _render_targets_html(site_targets)
                    except Exception as _tgt_exc:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "Target recommendations failed for %s: %s",
                            report.site_name, _tgt_exc,
                        )

                blocks.append(heading + chart_html_frag + legend_html + text_block + targets_html)

            separator = '<hr style="border:none;border-top:1px solid #30363d;margin:16px 0">'
            html_body = (
                '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                '<body style="background:#0d1117;color:#c9d1d9">'
                + moon_header
                + separator.join(blocks)
                + '</body></html>'
            )

            plain_body = "\n".join(body_lines).strip()
            mime_msg = MIMEMultipart("alternative")
            mime_msg["Subject"] = subject
            mime_msg["From"]    = smtp_user
            mime_msg["To"]      = email_to
            mime_msg.attach(MIMEText(plain_body, "plain"))
            mime_msg.attach(MIMEText(html_body,  "html"))

            try:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(smtp_user, smtp_password)
                    smtp.sendmail(smtp_user, [email_to], mime_msg.as_string())
                return EmailResult(sent=True)
            except smtplib.SMTPAuthenticationError:
                return EmailResult(sent=False, error="Auth failed — check your App Password.")
            except Exception as e:
                return EmailResult(sent=False, error=str(e))
        except Exception as _html_exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "HTML email failed, falling back to plain text: %s", _html_exc
            )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg.set_content("\n".join(body_lines).strip())

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg, from_addr=smtp_user, to_addrs=[email_to])
        return EmailResult(sent=True)
    except smtplib.SMTPAuthenticationError:
        return EmailResult(sent=False, error="Auth failed — check your App Password.")
    except Exception as e:
        return EmailResult(sent=False, error=str(e))


def send_test_email() -> EmailResult:
    """Send a one-line test email to verify credentials. Returns EmailResult — never raises."""
    from data_dir import ENV_FILE
    load_dotenv(ENV_FILE, override=True)
    smtp_user, smtp_password, smtp_host, smtp_port = _load_smtp_config()
    email_to = _clean(os.getenv("ALERT_EMAIL_TO")) or smtp_user

    if not smtp_user:
        return EmailResult(sent=False, error="Missing env var: SMTP_USER")
    if not smtp_password:
        return EmailResult(sent=False, error="Missing env var: SMTP_PASSWORD")
    for addr in (smtp_user, email_to):
        err = _validate_address(addr)
        if err:
            return EmailResult(sent=False, error=f"Invalid address: {err}")

    msg = EmailMessage()
    msg["Subject"] = "Astro Alert - Test Email"
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg.set_content("Your Astro Alert credentials are working correctly!")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg, from_addr=smtp_user, to_addrs=[email_to])
        return EmailResult(sent=True)
    except smtplib.SMTPAuthenticationError:
        return EmailResult(sent=False, error="Auth failed — check your App Password.")
    except Exception as e:
        return EmailResult(sent=False, error=str(e))
