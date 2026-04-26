# SMTP Provider-Neutral Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded Gmail SMTP settings with configurable provider-neutral SMTP, defaulting to Gmail, with a toggle in the Settings GUI.

**Architecture:** Rename `gmail_notifier.py` → `smtp_notifier.py` with env-driven host/port (Gmail defaults) and `SMTP_USER`/`SMTP_PASSWORD` vars (falling back to old `GMAIL_*` vars for backwards compat). Add a "Use a different email provider" checkbox in the Settings tab that reveals SMTP host/port fields.

**Tech Stack:** Python 3.11, tkinter, smtplib, python-dotenv

---

## File Map

| File | Change |
|------|--------|
| `smtp_notifier.py` | **Create** — renamed + updated version of `gmail_notifier.py` |
| `gmail_notifier.py` | **Delete** after all imports updated |
| `test_notifier.py` | **Modify** — update imports, ENV dict, patch paths, error assertions |
| `notifier.py` | **Modify** — update import |
| `astro_alert.py` | **Modify** — update import |
| `gui.py` | **Modify** — Settings tab: labels, checkbox, SMTP fields, cred methods |
| `test_gui.py` | **Modify** — update env var names, imports, add new SMTP checkbox tests |
| `README.md` | **Modify** — update env var docs, add provider table, update heading |

---

## Task 1: Create `smtp_notifier.py` and update `test_notifier.py`

**Files:**
- Create: `astro_alert/smtp_notifier.py`
- Modify: `astro_alert/test_notifier.py`

- [ ] **Step 1: Update test_notifier.py imports and ENV to target smtp_notifier**

Replace the top of `test_notifier.py` (lines 1–17):

```python
"""Tests for smtp_notifier.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from moon import MoonInfo
from smtp_notifier import (SiteReport, send_multi_site_alert, send_test_email,
                            _format_report, _clean, _validate_address)
from scorer import Score

ENV = {
    "SMTP_USER": "test@example.com",
    "SMTP_PASSWORD": "test-password",
    "ALERT_EMAIL_TO": "test@example.com",
}
```

- [ ] **Step 2: Update all patch paths and GMAIL_* references in test_notifier.py**

Run this to find all lines that need changing:
```bash
grep -n "gmail_notifier\|GMAIL_USER\|GMAIL_APP_PASSWORD" test_notifier.py
```

For each occurrence:
- `gmail_notifier.smtplib.SMTP` → `smtp_notifier.smtplib.SMTP`
- `gmail_notifier.load_dotenv` → `smtp_notifier.load_dotenv`
- `"GMAIL_USER"` → `"SMTP_USER"`
- `"GMAIL_APP_PASSWORD"` → `"SMTP_PASSWORD"`
- `assert "GMAIL_APP_PASSWORD" in result.error` → `assert "SMTP_PASSWORD" in result.error`

Also update line ~170 (missing-password test setup):
```python
incomplete = {k: v for k, v in ENV.items() if k != "SMTP_PASSWORD"}
    import os; os.environ.pop("SMTP_PASSWORD", None)
```

And line ~316 (send_test_email env):
```python
env = {"SMTP_USER": "me@example.com", "SMTP_PASSWORD": "pw"}
```

- [ ] **Step 3: Run tests to confirm they fail with ImportError**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_notifier.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'smtp_notifier'`

- [ ] **Step 4: Create `smtp_notifier.py`**

```python
"""Send go/no-go alerts via SMTP (defaults to Gmail)."""

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
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip()


def _validate_address(addr: str) -> Optional[str]:
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
        port = int(os.getenv("SMTP_PORT", DEFAULT_SMTP_PORT))
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
        f"[weather {score.weather_score}/40, seeing {score.seeing_score}/30, moon {score.moon_score}/30]",
    ]
    if score.warnings:
        lines.append("  " + " / ".join(score.warnings))
    return lines


def send_multi_site_alert(reports: list[SiteReport], night_label: str = "tonight") -> EmailResult:
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

    if not smtp_user or not smtp_password:
        return EmailResult(sent=False, error="Credentials not configured.")
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
```

- [ ] **Step 5: Run test_notifier.py and confirm all tests pass**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_notifier.py -v
```
Expected: all tests pass (same count as before).

- [ ] **Step 6: Commit**

```bash
git add smtp_notifier.py test_notifier.py
git commit -m "feat: rename gmail_notifier to smtp_notifier with provider-neutral SMTP config"
```

---

## Task 2: Update imports in `notifier.py` and `astro_alert.py`, delete `gmail_notifier.py`

**Files:**
- Modify: `astro_alert/notifier.py:3`
- Modify: `astro_alert/astro_alert.py:8`
- Delete: `astro_alert/gmail_notifier.py`

- [ ] **Step 1: Update notifier.py**

Change line 3:
```python
from smtp_notifier import SiteReport, send_multi_site_alert
```

- [ ] **Step 2: Update astro_alert.py**

Change line 8:
```python
from smtp_notifier import SiteReport, send_multi_site_alert
```

- [ ] **Step 3: Delete gmail_notifier.py**

```bash
cd /Users/pauldavis/astro_alert && git rm gmail_notifier.py
```

- [ ] **Step 4: Run the full test suite to confirm nothing broke**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_notifier.py test_cli.py test_scorer.py test_weather.py test_seeing.py test_moon.py test_site_manager.py test_scheduler.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add notifier.py astro_alert.py
git commit -m "chore: update imports from gmail_notifier to smtp_notifier"
```

---

## Task 3: Update `gui.py` Settings tab

**Files:**
- Modify: `astro_alert/gui.py`

- [ ] **Step 1: Update warning banner text (line ~205)**

Change:
```python
tk.Label(self._cred_warn, text="⚠  Gmail credentials not configured — alerts won't send.",
```
To:
```python
tk.Label(self._cred_warn, text="⚠  Email credentials not configured — alerts won't send.",
```

- [ ] **Step 2: Update Settings tab heading and field label (lines ~553, ~569)**

Change line ~553:
```python
ttk.Label(inner, text="Email Credentials",
          font=(FONT_PROP, 17, "bold")).pack(pady=(0, 5))
```

Change line ~569:
```python
("Email address",    self._cred_user_var, False),
```

Change tip text at line ~586:
```python
ttk.Label(card,
          text="Tip: use an App Password or your provider's equivalent, not your login password.",
          style="CardDim.TLabel").grid(
    row=len(fields), column=0, columnspan=3, pady=(4, 0), padx=16)
```

- [ ] **Step 3: Add SMTP checkbox and host/port fields to `_build_settings_tab`**

After the `card.pack(...)` block and before `btn_row = ttk.Frame(inner)`, insert:

```python
        self._smtp_custom_var = tk.BooleanVar(value=False)
        self._smtp_host_var   = tk.StringVar(value="smtp.gmail.com")
        self._smtp_port_var   = tk.StringVar(value="587")

        smtp_toggle_frame = ttk.Frame(inner)
        smtp_toggle_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            smtp_toggle_frame,
            text="Use a different email provider (custom SMTP)",
            variable=self._smtp_custom_var,
            command=self._on_smtp_toggle,
        ).pack(anchor="w", padx=16)

        self._smtp_detail_frame = ttk.Frame(inner, style="Card.TFrame")
        self._smtp_detail_frame.columnconfigure(1, weight=1)
        for row_idx, (label, var) in enumerate([
            ("SMTP host", self._smtp_host_var),
            ("SMTP port", self._smtp_port_var),
        ]):
            ttk.Label(self._smtp_detail_frame, text=label + ":", style="CardDim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=8, padx=(16, 12))
            ttk.Entry(self._smtp_detail_frame, textvariable=var,
                      font=(FONT_PROP, 12), width=36).grid(
                row=row_idx, column=1, sticky="ew", pady=8)
```

Note: `self._smtp_detail_frame` is NOT packed here — it only appears when the checkbox is ticked.

- [ ] **Step 4: Add `_on_smtp_toggle` method**

Add this method near `_toggle_password`:
```python
    def _on_smtp_toggle(self):
        if self._smtp_custom_var.get():
            self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12,
                                          before=self._smtp_detail_frame.master.pack_slaves()[-1])
        else:
            self._smtp_detail_frame.pack_forget()
```

Wait — to insert the detail frame between the toggle and the buttons cleanly, pack the detail frame directly after `smtp_toggle_frame` is created but keep it hidden. Use `pack_forget()` immediately after packing:

Replace Step 3's smtp_detail_frame lines with:
```python
        self._smtp_detail_frame = ttk.Frame(inner, style="Card.TFrame")
        self._smtp_detail_frame.columnconfigure(1, weight=1)
        self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
        self._smtp_detail_frame.pack_forget()  # hidden until checkbox ticked
        for row_idx, (label, var) in enumerate([
            ("SMTP host", self._smtp_host_var),
            ("SMTP port", self._smtp_port_var),
        ]):
            ttk.Label(self._smtp_detail_frame, text=label + ":", style="CardDim.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=8, padx=(16, 12))
            ttk.Entry(self._smtp_detail_frame, textvariable=var,
                      font=(FONT_PROP, 12), width=36).grid(
                row=row_idx, column=1, sticky="ew", pady=8)
```

And the toggle method:
```python
    def _on_smtp_toggle(self):
        if self._smtp_custom_var.get():
            self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
        else:
            self._smtp_detail_frame.pack_forget()
```

- [ ] **Step 5: Update `_load_credentials_to_form` (line ~648)**

Replace the method body:
```python
    def _load_credentials_to_form(self):
        from data_dir import ENV_FILE
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
        smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
        self._cred_user_var.set(smtp_user)
        self._cred_pass_var.set(smtp_pass)
        self._cred_to_var.set(vals.get("ALERT_EMAIL_TO", ""))
        self._home_lat_var.set(vals.get("HOME_LAT", ""))
        self._home_lon_var.set(vals.get("HOME_LON", ""))
        smtp_host = vals.get("SMTP_HOST", "")
        if smtp_host and smtp_host != "smtp.gmail.com":
            self._smtp_custom_var.set(True)
            self._smtp_host_var.set(smtp_host)
            self._smtp_port_var.set(vals.get("SMTP_PORT", "587"))
            self._smtp_detail_frame.pack(fill="x", ipadx=28, ipady=12)
```

- [ ] **Step 6: Update `_save_credentials` (line ~658)**

Replace the method body:
```python
    def _save_credentials(self):
        import unicodedata
        from data_dir import ENV_FILE
        from dotenv import set_key, unset_key
        def _norm(s): return unicodedata.normalize("NFKC", s).strip()
        smtp_user = _norm(self._cred_user_var.get())
        smtp_pass = _norm(self._cred_pass_var.get())
        alert_to  = _norm(self._cred_to_var.get())
        ENV_FILE.touch()
        if smtp_user:
            set_key(ENV_FILE, "SMTP_USER", smtp_user)
        if smtp_pass:
            set_key(ENV_FILE, "SMTP_PASSWORD", smtp_pass)
        if alert_to:
            set_key(ENV_FILE, "ALERT_EMAIL_TO", alert_to)
        else:
            unset_key(ENV_FILE, "ALERT_EMAIL_TO")
        if self._smtp_custom_var.get():
            smtp_host = _norm(self._smtp_host_var.get()) or "smtp.gmail.com"
            smtp_port = _norm(self._smtp_port_var.get()) or "587"
            set_key(ENV_FILE, "SMTP_HOST", smtp_host)
            set_key(ENV_FILE, "SMTP_PORT", smtp_port)
        else:
            unset_key(ENV_FILE, "SMTP_HOST")
            unset_key(ENV_FILE, "SMTP_PORT")
        self._refresh_cred_banner()
        self._set_status("Credentials saved.")
        messagebox.showinfo("Saved", "Credentials saved. Send a test email to verify.",
                            parent=self)
```

- [ ] **Step 7: Update `_do_test_email`, `_refresh_cred_banner`, `_check_first_run`**

`_do_test_email` (line ~755):
```python
    def _do_test_email(self):
        from smtp_notifier import send_test_email
        result = send_test_email()
        self.after(0, self._test_email_done, result)
```

`_refresh_cred_banner` (line ~769):
```python
    def _refresh_cred_banner(self):
        from data_dir import ENV_FILE
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
        smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
        has_creds = bool(smtp_user and smtp_pass)
        if has_creds:
            self._cred_warn.pack_forget()
        else:
            self._cred_warn.pack(fill="x", padx=0, pady=0, before=self._ctrl_frame)
```

`_check_first_run` (line ~779):
```python
    def _check_first_run(self):
        from data_dir import ENV_FILE
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        smtp_user = vals.get("SMTP_USER") or vals.get("GMAIL_USER", "")
        smtp_pass = vals.get("SMTP_PASSWORD") or vals.get("GMAIL_APP_PASSWORD", "")
        if not smtp_user or not smtp_pass:
            self._nb.select(self._tab_settings)
```

- [ ] **Step 8: Commit**

```bash
git add gui.py
git commit -m "feat: add custom SMTP toggle to Settings tab; rename Gmail fields to provider-neutral"
```

---

## Task 4: Update `test_gui.py`

**Files:**
- Modify: `astro_alert/test_gui.py`

- [ ] **Step 1: Update gmail_notifier imports and env var names in test_gui.py**

Run to find all references:
```bash
grep -n "gmail_notifier\|GMAIL_USER\|GMAIL_APP_PASSWORD" test_gui.py
```

Apply these replacements throughout:
- `from gmail_notifier import EmailResult` → `from smtp_notifier import EmailResult`
- `GMAIL_USER=test@example.com\nGMAIL_APP_PASSWORD=secret\n` → `SMTP_USER=test@example.com\nSMTP_PASSWORD=secret\n`
- `GMAIL_USER=u@g.com\nGMAIL_APP_PASSWORD=pw\n` → `SMTP_USER=u@g.com\nSMTP_PASSWORD=pw\n`
- `vals["GMAIL_USER"]` → `vals["SMTP_USER"]`
- `vals["GMAIL_APP_PASSWORD"]` → `vals["SMTP_PASSWORD"]`
- `assert "GMAIL_APP_PASSWORD" not in content` → `assert "SMTP_PASSWORD" not in content`

- [ ] **Step 2: Update `_load_credentials_to_form` test to use SMTP_USER**

Find the test that checks loaded credentials (line ~801). The env written to disk changes to `SMTP_USER` / `SMTP_PASSWORD`. The assertions on `_cred_user_var` and `_cred_pass_var` values stay the same.

- [ ] **Step 3: Add test for SMTP checkbox auto-tick on load**

Find the class that tests the Settings tab and add:
```python
def test_load_credentials_ticks_smtp_checkbox_for_custom_host(self, app, fake_env):
    fake_env.write_text(
        "SMTP_USER=me@outlook.com\nSMTP_PASSWORD=pw\n"
        "SMTP_HOST=smtp-mail.outlook.com\nSMTP_PORT=587\n"
    )
    app._load_credentials_to_form()
    assert app._smtp_custom_var.get() is True
    assert app._smtp_host_var.get() == "smtp-mail.outlook.com"
    assert app._smtp_port_var.get() == "587"

def test_load_credentials_does_not_tick_smtp_checkbox_for_gmail(self, app, fake_env):
    fake_env.write_text("SMTP_USER=me@gmail.com\nSMTP_PASSWORD=pw\n")
    app._load_credentials_to_form()
    assert app._smtp_custom_var.get() is False
```

- [ ] **Step 4: Add test for saving SMTP host/port when checkbox ticked**

```python
def test_save_credentials_writes_smtp_host_when_checkbox_ticked(self, app, fake_env):
    from dotenv import dotenv_values
    fake_env.touch()
    app._cred_user_var.set("me@outlook.com")
    app._cred_pass_var.set("mypassword")
    app._smtp_custom_var.set(True)
    app._smtp_host_var.set("smtp-mail.outlook.com")
    app._smtp_port_var.set("587")
    app._save_credentials()
    vals = dotenv_values(fake_env)
    assert vals["SMTP_USER"] == "me@outlook.com"
    assert vals["SMTP_HOST"] == "smtp-mail.outlook.com"
    assert vals["SMTP_PORT"] == "587"

def test_save_credentials_omits_smtp_host_when_checkbox_unticked(self, app, fake_env):
    from dotenv import dotenv_values
    fake_env.touch()
    app._cred_user_var.set("me@gmail.com")
    app._cred_pass_var.set("mypassword")
    app._smtp_custom_var.set(False)
    app._save_credentials()
    vals = dotenv_values(fake_env)
    assert "SMTP_HOST" not in vals
    assert "SMTP_PORT" not in vals
```

- [ ] **Step 5: Run test_gui.py to confirm all tests pass**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_gui.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/pauldavis/astro_alert && python -m pytest test_*.py -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add test_gui.py
git commit -m "test: update gui tests for smtp_notifier and add SMTP checkbox coverage"
```

---

## Task 5: Update README

**Files:**
- Modify: `astro_alert/README.md`

- [ ] **Step 1: Update credentials env var table**

Find the credentials block (around "Option B — manually") and replace the env var table:

```
SMTP_USER=you@example.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # App Password or provider equivalent (not your login password)
ALERT_EMAIL_TO=you@example.com      # optional — defaults to SMTP_USER
# Optional — only needed for non-Gmail providers:
SMTP_HOST=smtp.gmail.com            # defaults to smtp.gmail.com
SMTP_PORT=587                       # defaults to 587
```

- [ ] **Step 2: Add provider reference note and table**

After the credentials block, add:

```markdown
Gmail is the default. To use another provider, set `SMTP_HOST` and `SMTP_PORT` (or use the custom SMTP toggle in Settings):

| Provider | SMTP Host | Port |
|----------|-----------|------|
| Gmail | smtp.gmail.com | 587 |
| Outlook / Hotmail | smtp-mail.outlook.com | 587 |
| Yahoo Mail | smtp.mail.yahoo.com | 587 |
| iCloud Mail | smtp.mail.me.com | 587 |
```

- [ ] **Step 3: Update "Creating a Gmail App Password" heading**

Change heading to: `#### Gmail users: create an App Password`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for provider-neutral SMTP; add provider reference table"
```

---

## Self-Review

**Spec coverage:**
- ✅ SMTP_USER/SMTP_PASSWORD with GMAIL_* fallback — Task 1
- ✅ SMTP_HOST/SMTP_PORT with Gmail defaults — Task 1
- ✅ smtp_notifier.py (renamed from gmail_notifier.py) — Task 1
- ✅ Provider-neutral error messages — Task 1 (smtp_notifier.py)
- ✅ Import updates: notifier.py, astro_alert.py — Task 2
- ✅ GUI: "Email address" label, checkbox, SMTP fields — Task 3
- ✅ GUI: checkbox auto-ticks when SMTP_HOST differs from gmail default — Task 3
- ✅ GUI: Save Credentials writes/clears SMTP_HOST/SMTP_PORT — Task 3
- ✅ test_notifier.py updated — Task 1
- ✅ test_gui.py updated + new checkbox tests — Task 4
- ✅ README: env vars, provider table, heading — Task 5

**Type consistency:** `_load_smtp_config()` returns `tuple[str, str, str, int]` — used consistently in both `send_multi_site_alert` and `send_test_email`. `_smtp_custom_var` is `BooleanVar`, `_smtp_host_var`/`_smtp_port_var` are `StringVar` — used consistently in load, save, and toggle.

**No placeholders detected.**
