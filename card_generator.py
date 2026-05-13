"""Generate a nightly astrophotography report card as a PNG image."""

import base64
import html as _esc
import json
import logging
import zoneinfo
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)
_CARD_WIDTH = 900


@dataclass
class CardInput:
    site_name: str
    site_key: str
    site_bortle: int
    site_tz: str          # IANA timezone e.g. 'America/New_York'
    target_date: date
    score: object         # scorer.Score
    moon: object          # moon.MoonInfo
    targets: list         # list[TargetResult]
    equipment: str = "ZWO ASI2600MC-Air on Askar 120 APO"
    drive_min: Optional[int] = None


# ── AI narrative ─────────────────────────────────────────────────────────────

def generate_narrative(card: CardInput, api_key: str) -> dict:
    """Call OpenAI GPT-4o for narrative text. Falls back gracefully on any error."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        target_list = [
            {
                "name": t.name,
                "common_name": t.common_name,
                "type": t.type,
                "peak_alt_deg": round(t.peak_alt_deg, 1),
                "hours_visible": t.hours_visible,
                "peak_utc": t.transit_utc.strftime("%H:%M UTC") if t.transit_utc else None,
                "description": t.description,
                "size_arcmin": t.size_arcmin,
                "magnitude": t.magnitude,
            }
            for t in card.targets[:12]
        ]

        conditions = ", ".join(card.score.warnings) if card.score.warnings else "nominal"

        prompt = f"""You are an experienced astrophotographer writing a nightly report card.

Site: {card.site_name} (Bortle {card.site_bortle})
Date: {card.target_date.strftime('%B %d, %Y')}
Equipment: {card.equipment}
Score: {card.score.total}/100 ({'GO' if card.score.go else 'NO-GO'})
  Weather: {card.score.weather_score}%  Seeing: {card.score.seeing_score}%  Moon: {card.score.moon_score}%
Condition notes: {conditions}
Moon: {card.moon.phase_pct:.0f}% illuminated
Targets (sorted by peak altitude):
{json.dumps(target_list, indent=2)}

Return a JSON object with exactly these keys:
{{
  "banner_headline": "All-caps headline, max 60 chars, starts with YES or NO-GO",
  "banner_subtext": "One sentence, max 80 chars, key reason tonight is good or bad",
  "target_bullets": {{
    "<target name e.g. M8>": ["short bullet ≤8 words", "short bullet ≤8 words", "short bullet ≤8 words"]
  }},
  "game_plan": ["Specific step 1 for {card.equipment}", "Step 2", "Step 3"],
  "tip": "One technique tip for tonight, max 80 chars"
}}

Include bullets for each of the {min(len(card.targets), 6)} targets listed. Be concise."""

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.7,
        )
        result = json.loads(resp.choices[0].message.content)
        result["_source"] = "openai"
        return result

    except Exception as exc:
        _log.warning("OpenAI narrative failed (%s), using fallback", exc)
        return {**_fallback_narrative(card), "_source": "fallback"}


def _fallback_narrative(card: CardInput) -> dict:
    return {
        "banner_headline": "YES – TARGETS AVAILABLE TONIGHT" if card.score.go else "NO-GO TONIGHT",
        "banner_subtext": card.score.summary,
        "target_bullets": {
            t.name: [
                f"Peak {t.peak_alt_deg:.0f}° {_compass(t.peak_az_deg)}",
                f"Window: {t.hours_visible:.0f}h above 25°",
                t.description[:50] + ("…" if len(t.description) > 50 else ""),
            ]
            for t in card.targets[:12]
        },
        "game_plan": [
            "Set up, polar align, and cool the sensor",
            "Start with the brightest visible target",
            "Image until astronomical twilight",
        ],
        "tip": "Cool your camera 20–30 min before imaging for lowest noise floor.",
    }


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _b64_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _moon_emoji(phase_pct: float) -> str:
    thresholds = [(6, "🌑"), (25, "🌒"), (45, "🌓"), (55, "🌔"),
                  (75, "🌕"), (85, "🌖"), (95, "🌗")]
    for limit, emoji in thresholds:
        if phase_pct < limit:
            return emoji
    return "🌘"


def _local_time(utc_dt: Optional[datetime], tz_name: str) -> str:
    if utc_dt is None:
        return "—"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
        local = utc_dt.replace(tzinfo=timezone.utc).astimezone(tz)
        return local.strftime("%-I:%M %p")
    except Exception:
        return utc_dt.strftime("%H:%MZ")


def _compass(az_deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(az_deg / 22.5) % 16]


def _window_str(start_utc: Optional[datetime], end_utc: Optional[datetime], tz_name: str) -> str:
    if start_utc is None or end_utc is None:
        return ""
    s = _local_time(start_utc, tz_name)
    e = _local_time(end_utc, tz_name)
    return f"{s} – {e}"


def _score_cls(v: int) -> str:
    return "good" if v >= 70 else ("ok" if v >= 45 else "poor")


def _dominant_type(targets: list) -> str:
    if not targets:
        return "DEEP-SKY"
    top = [t.type for t in targets[:3]]
    if all("Nebula" in t for t in top):
        return "NEBULA"
    if all("Galaxy" in t for t in top):
        return "GALAXY"
    if all("Cluster" in t for t in top):
        return "CLUSTER"
    return "DEEP-SKY"


_RANK_LABELS = {
    1: "1st Choice", 2: "2nd Choice",  3: "3rd Choice",
    4: "4th Option", 5: "5th Option",  6: "6th Option",
    7: "7th Option", 8: "8th Option",  9: "9th Option",
    10: "Late Pick", 11: "Late Pick", 12: "Late Pick",
}


def _target_card_html(t, bullets: list, img_uri: Optional[str], rank: int, tz_name: str) -> str:
    img_block = (
        f'<img src="{img_uri}" class="timg" alt="{_esc.escape(t.name)}">'
        if img_uri else
        f'<div class="timg-ph">{_esc.escape(t.common_name)}</div>'
    )
    rank_label = _RANK_LABELS.get(rank, f"Option {rank}")
    bullet_li = "".join(f"<li>{_esc.escape(b)}</li>" for b in (bullets or [])[:3])
    win_str  = _window_str(t.window_start_utc, t.window_end_utc, tz_name)
    compass  = _compass(t.peak_az_deg)
    return f"""<div class="tcard">
  {img_block}
  <div class="tbody">
    <div class="trank">{rank_label}</div>
    <div class="tname">{_esc.escape(t.common_name)}</div>
    <div class="tcat">{_esc.escape(t.name)} · {_esc.escape(t.type)}</div>
    <ul class="tbullets">{bullet_li}</ul>
    <div class="tfooter">
      <span class="ttime">{_esc.escape(win_str)}</span>
      <span class="talt">Peak {t.peak_alt_deg:.0f}° {_esc.escape(compass)}</span>
    </div>
  </div>
</div>"""


# ── HTML card ─────────────────────────────────────────────────────────────────

_CSS = """
* { margin:0; padding:0; box-sizing:border-box }
body { width:900px; background:#08101c; color:#fff;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif }
.header { background:#0c1420; padding:18px 28px; display:flex;
          justify-content:space-between; align-items:flex-start;
          border-bottom:1px solid #152030 }
.site-name { font-size:28px; font-weight:800; letter-spacing:1px;
             text-transform:uppercase; color:#e8f4ff }
.site-sub { font-size:12px; color:#5080a0; margin-top:3px }
.hright { text-align:right }
.hdate { font-size:12px; color:#7090a0 }
.htime { font-size:17px; font-weight:600; color:#c0d8e8; margin-top:1px }
.hmoon { font-size:11px; color:#7090a0; margin-top:3px }
.banner { padding:13px 28px; display:flex; align-items:center; gap:14px }
.banner-go  { background:#0a2010; border-top:2px solid #1a5025;
              border-bottom:1px solid #1a4020 }
.banner-nogo { background:#200a0a; border-top:2px solid #501a1a;
               border-bottom:1px solid #401a1a }
.bicon { font-size:22px; flex-shrink:0 }
.bhl { font-size:17px; font-weight:700; letter-spacing:.4px }
.banner-go  .bhl { color:#3dba50 }
.banner-nogo .bhl { color:#e05050 }
.bsub { font-size:12px; margin-top:2px }
.banner-go  .bsub { color:#6aaa78 }
.banner-nogo .bsub { color:#aa6a6a }
.sec { font-size:11px; font-weight:700; letter-spacing:2px; color:#406080;
       padding:18px 28px 8px; text-transform:uppercase }
.tgrid { display:grid; gap:10px; padding:0 28px 12px }
.tgrid-3 { grid-template-columns:repeat(3,1fr) }
.tgrid-2 { grid-template-columns:repeat(2,1fr) }
.tgrid-1 { grid-template-columns:300px }
.tcard { background:#0c1828; border:1px solid #152535; border-radius:6px;
         overflow:hidden; display:flex; flex-direction:column }
.timg { width:100%; height:135px; object-fit:cover; display:block;
        filter:brightness(1.15) contrast(1.1) }
.timg-ph { width:100%; height:135px; background:#0a1628; display:flex;
           align-items:center; justify-content:center; color:#304050;
           font-size:12px; font-style:italic }
.tbody { padding:10px; flex:1; display:flex; flex-direction:column }
.trank { font-size:10px; font-weight:700; color:#3060a0;
         text-transform:uppercase; letter-spacing:1px }
.tname { font-size:15px; font-weight:700; margin-top:2px; color:#e0f0ff }
.tcat  { font-size:11px; color:#507090; margin-top:1px }
.tbullets { list-style:none; margin-top:8px; flex:1 }
.tbullets li { font-size:11px; color:#90b0c8; padding:1.5px 0;
               display:flex; align-items:flex-start; gap:5px }
.tbullets li::before { content:"✓"; color:#3dba50; flex-shrink:0;
                       font-size:10px; margin-top:1px }
.tfooter { margin-top:8px; padding-top:6px; border-top:1px solid #152535;
           display:flex; justify-content:space-between; font-size:10px }
.ttime { color:#a0c0d8 }
.talt  { color:#607080 }
.bottom { display:grid; grid-template-columns:1fr 1fr; gap:10px;
          padding:0 28px 14px }
.bcard { background:#0c1828; border:1px solid #152535; border-radius:6px;
         padding:14px }
.btitle { font-size:11px; font-weight:700; letter-spacing:1.5px; color:#406080;
          text-transform:uppercase; margin-bottom:10px }
.crow { display:flex; justify-content:space-between; align-items:center;
        padding:4px 0; font-size:12px; border-bottom:1px solid #0f1e2e }
.clabel { color:#607080 }
.cval { font-weight:600 }
.good { color:#3dba50 }
.ok   { color:#f0c040 }
.poor { color:#e05050 }
.gpitem { display:flex; gap:10px; align-items:flex-start; padding:5px 0;
          font-size:12px; color:#90b0c8; border-bottom:1px solid #0f1e2e }
.gpnum { background:#102040; color:#4080c0; width:20px; height:20px;
         border-radius:50%; display:flex; align-items:center;
         justify-content:center; font-size:10px; font-weight:700;
         flex-shrink:0; margin-top:1px }
.divider { height:1px; background:#152535; margin:0 28px }
.tip { display:flex; gap:12px; align-items:flex-start;
       padding:12px 28px 16px; font-size:12px; color:#90b0c8 }
.tipicon { font-size:18px; flex-shrink:0 }
"""


def build_card_html(card: CardInput, narrative: dict, dso_image_uris: dict[str, str]) -> str:
    """Return a complete HTML document for the report card."""
    go = card.score.go
    moon = card.moon
    bullets_map = narrative.get("target_bullets", {})
    targets = card.targets

    # Header
    try:
        tz = zoneinfo.ZoneInfo(card.site_tz)
        now_local = datetime.now(tz)
        date_str = now_local.strftime("%B %-d, %Y")
        time_str = now_local.strftime("%-I:%M %p %Z")
    except Exception:
        date_str = card.target_date.strftime("%B %d, %Y")
        time_str = ""

    moon_text = f"{_moon_emoji(moon.phase_pct)} {moon.phase_pct:.0f}% illuminated"
    if moon.set_utc:
        moon_text += f" · sets {_local_time(moon.set_utc, card.site_tz)}"

    drive_str = f" · {card.drive_min} min drive" if card.drive_min else ""
    site_sub = f"Bortle {card.site_bortle}{drive_str}"

    # Banner
    banner_cls = "banner banner-go" if go else "banner banner-nogo"
    banner_icon = "✅" if go else "❌"
    banner_hl = _esc.escape(narrative.get("banner_headline", ""))
    banner_sub = _esc.escape(narrative.get("banner_subtext", ""))

    # Target sections
    def _cards(ts, rank_start):
        out = ""
        for i, t in enumerate(ts):
            bulls = bullets_map.get(t.name) or bullets_map.get(t.common_name) or []
            img_uri = dso_image_uris.get(t.name)
            out += _target_card_html(t, bulls, img_uri, rank_start + i, card.site_tz)
        return out

    top3  = targets[:3]
    mid6  = targets[3:9]
    late3 = targets[9:12]

    top3_html  = _cards(top3,   1)
    mid6_html  = _cards(mid6,   4)
    late3_html = _cards(late3, 10)

    type_label = _dominant_type(targets)

    top_section = ""
    if top3:
        n = len(top3)
        grid_cls = f"tgrid tgrid-{n}"
        top_section = (
            f'<div class="sec">Best {type_label} Targets Tonight</div>'
            f'<div class="{grid_cls}">{top3_html}</div>'
        )

    mid_section = ""
    if mid6:
        mid_section = (
            f'<div class="sec">Other Great Options</div>'
            f'<div class="tgrid tgrid-3">{mid6_html}</div>'
        )

    late_section = ""
    if late3:
        n = len(late3)
        grid_cls = f"tgrid tgrid-{n}"
        late_section = (
            f'<div class="sec">Late Night Picks</div>'
            f'<div class="{grid_cls}">{late3_html}</div>'
        )

    no_targets_msg = ""
    if not targets:
        no_targets_msg = (
            '<div style="padding:20px 28px;color:#7090a0;font-size:14px">'
            'No targets above 25° during the imaging window tonight.'
            '</div>'
        )

    # Conditions
    cond_rows = [
        ("Weather", f"{card.score.weather_score}%", _score_cls(card.score.weather_score)),
        ("Seeing",  f"{card.score.seeing_score}%",  _score_cls(card.score.seeing_score)),
        ("Light Pollution", f"Bortle {card.site_bortle}",
         _score_cls(max(0, 100 - (card.site_bortle - 1) * 12))),
        ("Moon",    f"{moon.phase_pct:.0f}%",        _score_cls(card.score.moon_score)),
        ("Overall", f"{card.score.total}/100",       _score_cls(card.score.total)),
    ]
    cond_html = "".join(
        f'<div class="crow"><span class="clabel">{r[0]}</span>'
        f'<span class="cval {r[2]}">{r[1]}</span></div>'
        for r in cond_rows
    )

    # Game plan
    game_plan = narrative.get("game_plan", [])
    gp_html = "".join(
        f'<div class="gpitem"><span class="gpnum">{i + 1}</span>'
        f'<span>{_esc.escape(step)}</span></div>'
        for i, step in enumerate(game_plan[:3])
    )

    tip = _esc.escape(narrative.get("tip", ""))
    equip = _esc.escape(card.equipment.upper())

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>

<div class="header">
  <div>
    <div class="site-name">{_esc.escape(card.site_name)}</div>
    <div class="site-sub">{_esc.escape(site_sub)}</div>
  </div>
  <div class="hright">
    <div class="hdate">{date_str}</div>
    <div class="htime">{time_str}</div>
    <div class="hmoon">{_esc.escape(moon_text)}</div>
  </div>
</div>

<div class="{banner_cls}">
  <div class="bicon">{banner_icon}</div>
  <div>
    <div class="bhl">{banner_hl}</div>
    <div class="bsub">{banner_sub}</div>
  </div>
</div>

{no_targets_msg}{top_section}{mid_section}{late_section}

<div class="sec">Tonight&apos;s Conditions &amp; Game Plan</div>
<div class="bottom">
  <div class="bcard">
    <div class="btitle">Conditions</div>
    {cond_html}
  </div>
  <div class="bcard">
    <div class="btitle">Game Plan · {equip}</div>
    {gp_html}
  </div>
</div>

<div class="divider"></div>
<div class="tip">
  <div class="tipicon">💡</div>
  <div><strong>TIP:</strong> {tip}</div>
</div>

</body></html>"""


# ── PNG rendering ─────────────────────────────────────────────────────────────

def _chromium_executable() -> Optional[str]:
    """Return path to bundled Chromium when running as a PyInstaller app, else None."""
    import sys, os
    if not getattr(sys, "frozen", False):
        return None
    base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    for candidate in [
        base / "chromium" / "chrome-win" / "chrome.exe",   # Windows Playwright layout
        base / "chromium" / "chrome",                       # Linux
        base / "chromium" / "chrome.exe",                   # Windows flat (fallback)
        base / "chromium" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",  # macOS
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def render_card_png(html: str, output_path: Path) -> Path:
    """Render the HTML card to a PNG using playwright (sync API)."""
    import os
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # When bundled, point Playwright at the embedded browser.
    chromium_exe = _chromium_executable()
    if chromium_exe:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(chromium_exe).parent.parent.parent))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_exe)
        page = browser.new_page(
            viewport={"width": _CARD_WIDTH, "height": 900},
            device_scale_factor=2,
        )
        page.set_content(html, wait_until="domcontentloaded")
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()

    return output_path


# ── Top-level entry point ─────────────────────────────────────────────────────

def generate_site_card(
    card: CardInput,
    openai_key: str,
    output_dir: Path,
) -> tuple[Optional[Path], bool]:
    """Generate a report card PNG for one site. Returns (path, ai_used) or (None, False)."""
    try:
        from dso_images import fetch_dso_image

        dso_uris: dict[str, str] = {}
        for t in card.targets[:12]:
            img_bytes = fetch_dso_image(t.name, t.ra, t.dec, t.size_arcmin, obj_type=t.type)
            if img_bytes:
                dso_uris[t.name] = _b64_uri(img_bytes)

        if openai_key:
            narrative = generate_narrative(card, openai_key)
        else:
            narrative = {**_fallback_narrative(card), "_source": "fallback"}

        ai_used = narrative.get("_source") == "openai"
        _log.info("Narrative source for %s: %s", card.site_name, narrative.get("_source", "openai"))
        html = build_card_html(card, narrative, dso_uris)

        safe_key = card.site_key.replace("/", "_").replace(" ", "_")
        out_path = Path(output_dir) / f"{safe_key}_{card.target_date.isoformat()}.png"
        return render_card_png(html, out_path), ai_used

    except Exception as exc:
        _log.error("Card generation failed for %s: %s", card.site_name, exc)
        return None, False
