"""Send go/no-go alerts — email only (SMS pending carrier registration)."""

from gmail_notifier import SiteReport, send_multi_site_alert


def send_alert_with_fallback(reports: list[SiteReport]) -> dict:
    result = send_multi_site_alert(reports)
    if result.sent:
        return {"channel": "email", "success": True, "detail": "email sent"}
    return {"channel": "none", "success": False, "detail": result.error}
