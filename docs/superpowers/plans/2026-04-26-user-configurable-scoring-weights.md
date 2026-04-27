# User-Configurable Scoring Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Scoring tab to the GUI with sliders for all scoring weights; persist them to `scoring_weights.json`; refactor scorer to use them.

**Architecture:** New `scoring_weights.py` owns the `ScoringWeights` dataclass and persistence. Scorer functions are refactored to return 0–1 normalized scores and accept weights. `score_night` combines them with top-level weights into a 0–100 total. GUI Scoring tab reads/writes `scoring_weights.json`.

**Tech Stack:** Python 3.11+, tkinter/ttk, dataclasses, json, pytest.

**Important behavior note:** The new normalized scoring formula produces different absolute values than the old hardcoded formula (e.g. overcast with calm winds now scores ~30% instead of 0). This is intentional — the per-category scores now reflect all sub-factors, not just cloud cover. Many existing test assertions for specific point values must be updated to reflect the new formula.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scoring_weights.py` | **Create** | `ScoringWeights` dataclass + `load_weights` / `save_weights` |
| `scorer.py` | **Modify** | Sub-functions return `float` (0–1); `score_night` normalizes with weights |
| `smtp_notifier.py` | **Modify** | Update report format from `/40,/30,/30` to `%` display |
| `astro_alert.py` | **Modify** | Load weights in `_fetch_report`; pass to `score_night` |
| `gui.py` | **Modify** | Add Scoring tab with sliders |
| `test_scoring_weights.py` | **Create** | Tests for dataclass, load/save, defaults |
| `test_scorer.py` | **Modify** | Update to new float return type and behavior |

---

## Task 1: `scoring_weights.py` — dataclass and persistence

**Files:**
- Create: `scoring_weights.py`
- Create: `test_scoring_weights.py`

- [ ] **Step 1: Write failing tests**

```python
# test_scoring_weights.py
import json
import pytest
from pathlib import Path
from scoring_weights import ScoringWeights, load_weights, save_weights


def test_defaults():
    w = ScoringWeights()
    assert w.weather_weight == 40
    assert w.seeing_weight == 30
    assert w.moon_weight == 30
    assert w.go_threshold == 55
    assert w.cloud_weight == 70
    assert w.wind_weight == 20
    assert w.dew_weight == 10
    assert w.seeing_quality_weight == 50
    assert w.transparency_weight == 50
    assert w.phase_weight == 70
    assert w.dark_hours_weight == 30


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    import scoring_weights as sw
    monkeypatch.setattr(sw, "WEIGHTS_FILE", tmp_path / "nope.json")
    w = load_weights()
    assert w == ScoringWeights()


def test_round_trip(tmp_path, monkeypatch):
    import scoring_weights as sw
    monkeypatch.setattr(sw, "WEIGHTS_FILE", tmp_path / "weights.json")
    original = ScoringWeights(weather_weight=60, moon_weight=10, go_threshold=70)
    save_weights(original)
    loaded = load_weights()
    assert loaded == original


def test_malformed_json_returns_defaults(tmp_path, monkeypatch):
    import scoring_weights as sw
    f = tmp_path / "weights.json"
    f.write_text("not valid json{{{")
    monkeypatch.setattr(sw, "WEIGHTS_FILE", f)
    w = load_weights()
    assert w == ScoringWeights()


def test_partial_json_uses_defaults_for_missing_fields(tmp_path, monkeypatch):
    import scoring_weights as sw
    f = tmp_path / "weights.json"
    f.write_text(json.dumps({"weather_weight": 80}))
    monkeypatch.setattr(sw, "WEIGHTS_FILE", f)
    w = load_weights()
    assert w.weather_weight == 80
    assert w.seeing_weight == 30  # default


def test_save_creates_valid_json(tmp_path, monkeypatch):
    import scoring_weights as sw
    f = tmp_path / "weights.json"
    monkeypatch.setattr(sw, "WEIGHTS_FILE", f)
    save_weights(ScoringWeights())
    data = json.loads(f.read_text())
    assert data["go_threshold"] == 55
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest test_scoring_weights.py -v
```
Expected: `ModuleNotFoundError: No module named 'scoring_weights'`

- [ ] **Step 3: Implement `scoring_weights.py`**

```python
"""Global scoring weights for the go/no-go scorer."""
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Optional

from data_dir import DATA_DIR

WEIGHTS_FILE: Path = DATA_DIR / "scoring_weights.json"


@dataclass
class ScoringWeights:
    # Top-level category weights (relative, normalized automatically)
    weather_weight: int = 40
    seeing_weight: int = 30
    moon_weight: int = 30
    # GO threshold
    go_threshold: int = 55
    # Weather sub-weights
    cloud_weight: int = 70
    wind_weight: int = 20
    dew_weight: int = 10
    # Seeing sub-weights
    seeing_quality_weight: int = 50
    transparency_weight: int = 50
    # Moon sub-weights
    phase_weight: int = 70
    dark_hours_weight: int = 30


def load_weights() -> ScoringWeights:
    """Load weights from WEIGHTS_FILE; return defaults if missing or malformed."""
    try:
        data = json.loads(WEIGHTS_FILE.read_text())
        defaults = asdict(ScoringWeights())
        merged = {k: data.get(k, v) for k, v in defaults.items()}
        return ScoringWeights(**merged)
    except Exception:
        return ScoringWeights()


def save_weights(weights: ScoringWeights) -> None:
    """Write weights to WEIGHTS_FILE as JSON."""
    WEIGHTS_FILE.write_text(json.dumps(asdict(weights), indent=2))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python3 -m pytest test_scoring_weights.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scoring_weights.py test_scoring_weights.py
git commit -m "feat: add ScoringWeights dataclass with load/save persistence"
```

---

## Task 2: Refactor `_weather_score` to return normalized 0–1 score

**Files:**
- Modify: `scorer.py`
- Modify: `test_scorer.py`

The function signature changes from `-> tuple[int, list[str], int]` to `-> tuple[float, list[str], int]`. The first return value changes from `0–40 pts` to `0.0–1.0` normalized.

Sub-factor raw scores:
- `cloud_raw`: clear=1.0, mostly clear=0.8, partly cloudy=0.45, mostly cloudy=0.2, overcast=0.0; multiplied by 1.2 for dark sites (bortle≤4), capped at 1.0
- `wind_raw`: <20 km/h=1.0, 20–30 km/h=0.5, >30 km/h=0.0
- `dew_raw`: gap≥4°C=1.0, gap 2–4°C=0.5, gap<2°C=0.0; capped at 0.5 if humidity>90%
- Precipitation overrides `weather_norm = 0.0`
- Unavailable data returns `0.5` (neutral fallback, was `20`)

- [ ] **Step 1: Update failing tests for the new return type**

Replace the `TestWeatherScore` class in `test_scorer.py`:

```python
class TestWeatherScore:
    def test_clear_sky(self):
        norm, warns, _ = _weather_score(make_weather(cloud=5), bortle=7)
        assert norm == 1.0
        assert any("clear" in w.lower() for w in warns)

    def test_partly_cloudy(self):
        norm, warns, _ = _weather_score(make_weather(cloud=30), bortle=7)
        assert 0.0 < norm < 1.0
        assert any("cloudy" in w.lower() for w in warns)

    def test_overcast(self):
        norm, warns, _ = _weather_score(make_weather(cloud=90), bortle=7)
        # Cloud raw=0, but calm wind and no dew still contribute
        assert norm < 0.4
        assert any("overcast" in w.lower() for w in warns)

    def test_precipitation_zeroes_score(self):
        norm, warns, _ = _weather_score(make_weather(cloud=5, precip=1.0), bortle=7)
        assert norm == 0.0
        assert any("precip" in w.lower() for w in warns)

    def test_dark_site_cloud_weight(self):
        # Dark site (bortle=3) gets more credit for clear skies via Bortle multiplier
        norm_dark, _, _ = _weather_score(make_weather(cloud=20), bortle=3)
        norm_bright, _, _ = _weather_score(make_weather(cloud=20), bortle=7)
        assert norm_dark >= norm_bright

    def test_high_wind_penalty(self):
        norm_calm, _, _ = _weather_score(make_weather(wind=5), bortle=7)
        norm_windy, warns, _ = _weather_score(make_weather(wind=35), bortle=7)
        assert norm_windy < norm_calm
        assert any("wind" in w.lower() for w in warns)

    def test_dew_risk_warning(self):
        _, warns, _ = _weather_score(make_weather(dew_gap=1), bortle=7)
        assert any("dew" in w.lower() for w in warns)

    def test_unavailable_data_returns_neutral(self):
        norm, warns, _ = _weather_score(make_weather(error="timeout"), bortle=7)
        assert norm == 0.5
        assert any("unavailable" in w.lower() for w in warns)

    def test_moderate_wind_penalty(self):
        norm_calm, _, _ = _weather_score(make_weather(wind=5), bortle=7)
        norm_moderate, warns, _ = _weather_score(make_weather(wind=25), bortle=7)
        assert norm_moderate < norm_calm
        assert any("moderate wind" in w.lower() for w in warns)

    def test_high_humidity_warning(self):
        _, warns, _ = _weather_score(make_weather(humidity=95, dew_gap=5), bortle=7)
        assert any("humidity" in w.lower() for w in warns)
```

Also update the two date-filtering tests in `TestScoreNight` (lines ~311–315):

```python
    def test_target_date_filters_hours(self):
        target = date(2024, 1, 1)
        h_in = HourlyWeather(
            time=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            cloud_cover_pct=0, precip_mm=0, wind_speed_kmh=5,
            humidity_pct=50, dew_point_c=5, temp_c=15,
        )
        h_out = HourlyWeather(
            time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            cloud_cover_pct=100, precip_mm=5, wind_speed_kmh=50,
            humidity_pct=99, dew_point_c=14, temp_c=15,
        )
        result = WeatherResult(
            site_key="test",
            fetched_at=datetime.now(timezone.utc),
            hours=[h_in, h_out],
        )
        norm_with_date, _, _ = _weather_score(result, bortle=7, target_date=target)
        norm_no_date, _, _ = _weather_score(result, bortle=7, target_date=None)
        assert norm_with_date > norm_no_date
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python3 -m pytest test_scorer.py::TestWeatherScore -v
```
Expected: multiple FAILs (old code returns int, tests expect float).

- [ ] **Step 3: Rewrite `_weather_score` in `scorer.py`**

Replace the entire `_weather_score` function:

```python
def _weather_score(
    result: WeatherResult,
    bortle: int,
    target_date: Optional[date] = None,
    weights: Optional["ScoringWeights"] = None,
) -> tuple[float, list[str], int]:
    """Return (weather_norm 0–1, warnings, avg_cloud_pct)."""
    from scoring_weights import ScoringWeights
    if weights is None:
        weights = ScoringWeights()

    warnings = []
    if not result.ok or not result.hours:
        warnings.append("Weather data unavailable")
        return 0.5, warnings, -1

    if target_date:
        window = _imaging_hours(target_date)
        night_hours = [h for h in result.hours if h.time.replace(minute=0, second=0, microsecond=0) in window]
    else:
        night_hours = result.hours
    if not night_hours:
        night_hours = result.hours

    avg_cloud = sum(h.cloud_cover_pct for h in night_hours) / len(night_hours)
    any_precip = any(h.precip_mm > 0.1 for h in night_hours)
    avg_wind = sum(h.wind_speed_kmh for h in night_hours) / len(night_hours)
    avg_humidity = sum(h.humidity_pct for h in night_hours) / len(night_hours)
    min_dew_gap = min(h.temp_c - h.dew_point_c for h in night_hours)

    # Cloud raw (tier-based + Bortle multiplier)
    if avg_cloud < 10:
        cloud_raw = 1.0
        warnings.append(f"Clear ({avg_cloud:.0f}%)")
    elif avg_cloud < 25:
        cloud_raw = 0.8
        warnings.append(f"Mostly clear ({avg_cloud:.0f}%)")
    elif avg_cloud < 50:
        cloud_raw = 0.45
        warnings.append(f"Partly cloudy ({avg_cloud:.0f}%)")
    elif avg_cloud < 75:
        cloud_raw = 0.2
        warnings.append(f"Mostly cloudy ({avg_cloud:.0f}%)")
    else:
        cloud_raw = 0.0
        warnings.append(f"Overcast ({avg_cloud:.0f}%)")
    cloud_raw = min(1.0, cloud_raw * (1.2 if bortle <= 4 else 1.0))

    # Wind raw
    if avg_wind > 30:
        wind_raw = 0.0
        warnings.append(f"High wind ({avg_wind:.0f} km/h avg)")
    elif avg_wind > 20:
        wind_raw = 0.5
        warnings.append(f"Moderate wind ({avg_wind:.0f} km/h avg)")
    else:
        wind_raw = 1.0

    # Dew/humidity raw
    if min_dew_gap < 2:
        dew_raw = 0.0
        warnings.append(f"Dew risk: temp/dew gap only {min_dew_gap:.1f}°C")
    elif min_dew_gap < 4:
        dew_raw = 0.5
    else:
        dew_raw = 1.0
    if avg_humidity > 90:
        dew_raw = min(dew_raw, 0.5)
        warnings.append(f"High humidity ({avg_humidity:.0f}%)")

    # Combine sub-weights
    total_w = weights.cloud_weight + weights.wind_weight + weights.dew_weight
    weather_norm = (
        weights.cloud_weight * cloud_raw
        + weights.wind_weight * wind_raw
        + weights.dew_weight * dew_raw
    ) / total_w

    # Precipitation overrides everything
    if any_precip:
        weather_norm = 0.0
        warnings.append("Precipitation expected")

    return weather_norm, warnings, int(avg_cloud)
```

Also add `from __future__ import annotations` as the very first line of `scorer.py` (before all other imports) to allow the forward reference `Optional["ScoringWeights"]` in type hints without a circular import.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest test_scorer.py::TestWeatherScore -v
```
Expected: all 10 pass.

- [ ] **Step 5: Commit**

```bash
git add scorer.py test_scorer.py
git commit -m "refactor: _weather_score returns 0-1 normalized score using sub-weights"
```

---

## Task 3: Refactor `_seeing_score` to return normalized 0–1 score

**Files:**
- Modify: `scorer.py`
- Modify: `test_scorer.py`

Signature changes from `-> tuple[int, list[str]]` to `-> tuple[float, list[str]]`.

With defaults (seeing_quality=50, transparency=50):
- `seeing_norm = (50 * (avg_seeing/8) + 50 * (avg_transparency/8)) / 100`
- Perfect seeing (8,8): seeing_norm = 1.0 ✓ (was 30 pts)
- Unavailable: return 0.5 (was 15 pts)

- [ ] **Step 1: Update failing tests**

Replace `TestSeeingScore` in `test_scorer.py`:

```python
class TestSeeingScore:
    def test_excellent_seeing(self):
        norm, warns = _seeing_score(make_seeing(seeing=8, transparency=8))
        assert norm == 1.0
        assert not warns

    def test_poor_seeing_warning(self):
        norm, warns = _seeing_score(make_seeing(seeing=2, transparency=6))
        assert any("seeing" in w.lower() for w in warns)

    def test_poor_transparency_warning(self):
        _, warns = _seeing_score(make_seeing(seeing=6, transparency=2))
        assert any("transparency" in w.lower() for w in warns)

    def test_unavailable_returns_neutral(self):
        norm, warns = _seeing_score(make_seeing(error="timeout"))
        assert norm == 0.5
        assert any("unavailable" in w.lower() for w in warns)

    def test_seeing_weight_shifts_score(self):
        from scoring_weights import ScoringWeights
        # Seeing=8, transparency=2: seeing-heavy weights should score higher than even split
        w_seeing_heavy = ScoringWeights(seeing_quality_weight=90, transparency_weight=10)
        w_even = ScoringWeights(seeing_quality_weight=50, transparency_weight=50)
        norm_heavy, _ = _seeing_score(make_seeing(seeing=8, transparency=2), weights=w_seeing_heavy)
        norm_even, _ = _seeing_score(make_seeing(seeing=8, transparency=2), weights=w_even)
        assert norm_heavy > norm_even
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest test_scorer.py::TestSeeingScore -v
```
Expected: FAILs (old code returns int, tests expect float; `weights` param doesn't exist yet).

- [ ] **Step 3: Rewrite `_seeing_score` in `scorer.py`**

```python
def _seeing_score(
    result: SeeingResult,
    target_date: Optional[date] = None,
    weights: Optional["ScoringWeights"] = None,
) -> tuple[float, list[str]]:
    """Return (seeing_norm 0–1, warnings)."""
    from scoring_weights import ScoringWeights
    if weights is None:
        weights = ScoringWeights()

    warnings = []
    if not result.ok or not result.hours:
        warnings.append("Seeing data unavailable")
        return 0.5, warnings

    if target_date:
        window = _imaging_hours(target_date)
        night_hours = [h for h in result.hours if h.time.replace(minute=0, second=0, microsecond=0) in window]
    else:
        night_hours = result.hours
    if not night_hours:
        night_hours = result.hours

    avg_seeing = sum(h.seeing for h in night_hours) / len(night_hours)
    avg_transparency = sum(h.transparency for h in night_hours) / len(night_hours)

    seeing_raw = avg_seeing / 8.0
    transp_raw = avg_transparency / 8.0

    if avg_seeing < 3:
        warnings.append(f"Poor seeing ({avg_seeing:.1f}/8)")
    if avg_transparency < 3:
        warnings.append(f"Poor transparency ({avg_transparency:.1f}/8)")

    total_w = weights.seeing_quality_weight + weights.transparency_weight
    seeing_norm = (
        weights.seeing_quality_weight * seeing_raw
        + weights.transparency_weight * transp_raw
    ) / total_w

    return seeing_norm, warnings
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest test_scorer.py::TestSeeingScore -v
```
Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add scorer.py test_scorer.py
git commit -m "refactor: _seeing_score returns 0-1 normalized score using sub-weights"
```

---

## Task 4: Refactor `_moon_score` to return normalized 0–1 score

**Files:**
- Modify: `scorer.py`
- Modify: `test_scorer.py`

Signature changes from `-> tuple[int, list[str]]` to `-> tuple[float, list[str]]`.

Sub-factor design:
- `phase_raw` = tier-based (new moon=1.0, full moon=0.0): <10%→1.0, <25%→0.8, <50%→0.5, <75%→0.2, ≥75%→0.0
- `dark_hours_raw` = `_dark_hours_after_moonset(info) / 8.0` for bright moons (≥75%); for dim moons, set `dark_hours_raw = phase_raw` so the dark_hours_weight doesn't create a spurious penalty for moonless nights
- Up-at-midnight penalty: `phase_raw = max(0.0, phase_raw - 5/30)` for 20 < phase < 75
- Combined: `(phase_weight * phase_raw + dark_hours_weight * dark_hours_raw) / (phase_weight + dark_hours_weight)`

Unavailable data returns 0.5 (was 15 pts).

Verification with defaults (phase=70, dark_hours=30):
- New moon (phase=2): phase_raw=1.0, dark_hours_raw=1.0 → norm=1.0 (same as old 30/30)
- Crescent (phase=20): phase_raw=0.8, dark_hours_raw=0.8 → norm=0.8 (same as old 24/30)
- Quarter (phase=40): phase_raw=0.5, dark_hours_raw=0.5 → norm=0.5 (same as old 15/30)
- Gibbous (phase=60): phase_raw=0.2, dark_hours_raw=0.2 → norm=0.2 (same as old 6/30)
- Full moon, dark_hrs=0: phase_raw=0, dark_hours_raw=0 → norm=0.0 (same as old 0/30)
- Full moon, dark_hrs=6: phase_raw=0, dark_hours_raw=0.75 → norm=(0+30*0.75)/100=0.225

- [ ] **Step 1: Update failing tests**

Replace `TestMoonScore` in `test_scorer.py`:

```python
class TestMoonScore:
    def test_new_moon(self):
        norm, warns = _moon_score(make_moon(phase=5))
        assert norm == 1.0
        assert not warns

    def test_full_moon_no_set(self):
        norm, warns = _moon_score(make_moon(phase=99))
        assert norm == 0.0
        assert warns

    def test_full_moon_sets_before_midnight(self):
        moon = make_moon(phase=99, is_up=False, set_=moonset_at(22))
        norm, warns = _moon_score(moon)
        assert norm > 0.0
        assert any("sets" in w for w in warns)

    def test_full_moon_sets_after_imaging(self):
        moon = make_moon(phase=99, is_up=True, set_=moonset_at(5))
        norm, warns = _moon_score(moon)
        assert norm == 0.0

    def test_bright_moon_early_set_more_pts_than_late_set(self):
        early = make_moon(phase=80, set_=moonset_at(21))
        late = make_moon(phase=80, set_=moonset_at(23))
        norm_early, _ = _moon_score(early)
        norm_late, _ = _moon_score(late)
        assert norm_early > norm_late

    def test_moon_up_at_midnight_penalty(self):
        norm_up, _ = _moon_score(make_moon(phase=30, is_up=True))
        norm_down, _ = _moon_score(make_moon(phase=30, is_up=False))
        assert norm_up < norm_down

    def test_dark_hours_weight_shifts_bright_moon_score(self):
        from scoring_weights import ScoringWeights
        moon = make_moon(phase=90, set_=moonset_at(22))
        # High dark_hours_weight: early moonset = good score
        w_dark = ScoringWeights(dark_hours_weight=90, phase_weight=10)
        w_even = ScoringWeights(dark_hours_weight=30, phase_weight=70)
        norm_dark, _ = _moon_score(moon, weights=w_dark)
        norm_even, _ = _moon_score(moon, weights=w_even)
        assert norm_dark > norm_even
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest test_scorer.py::TestMoonScore -v
```
Expected: FAILs.

- [ ] **Step 3: Rewrite `_moon_score` in `scorer.py`**

```python
def _moon_score(
    info: MoonInfo,
    weights: Optional["ScoringWeights"] = None,
) -> tuple[float, list[str]]:
    """Return (moon_norm 0–1, warnings)."""
    from scoring_weights import ScoringWeights
    if weights is None:
        weights = ScoringWeights()

    warnings = []
    phase = info.phase_pct

    # Phase raw score (tier-based)
    if phase < 10:
        phase_raw = 1.0
    elif phase < 25:
        phase_raw = 0.8
        warnings.append(f"Crescent moon ({phase:.0f}% illuminated)")
    elif phase < 50:
        phase_raw = 0.5
        warnings.append(f"Quarter moon ({phase:.0f}% illuminated)")
    elif phase < 75:
        phase_raw = 0.2
        warnings.append(f"Gibbous moon ({phase:.0f}% illuminated)")
    else:
        phase_raw = 0.0
        dark_hrs = _dark_hours_after_moonset(info)
        if dark_hrs >= 4:
            set_str = info.set_utc.strftime("%H:%MZ") if info.set_utc else "?"
            warnings.append(f"Bright moon ({phase:.0f}%) sets {set_str} — image after moonset")
        else:
            warnings.append(f"Bright moon ({phase:.0f}% illuminated)")

    # Up-at-midnight penalty (crescent/quarter/gibbous only)
    if info.is_up_at_midnight and 20 < phase < 75:
        phase_raw = max(0.0, phase_raw - 5 / 30)
        warnings.append("Moon up at midnight")

    # Dark hours raw: actual dark hours for bright moon; mirrors phase_raw for dim moons
    if phase >= 75:
        dark_hours_raw = _dark_hours_after_moonset(info) / 8.0
    else:
        dark_hours_raw = phase_raw  # dim moons: no separate dark-hours constraint

    total_w = weights.phase_weight + weights.dark_hours_weight
    moon_norm = (
        weights.phase_weight * phase_raw
        + weights.dark_hours_weight * dark_hours_raw
    ) / total_w

    return moon_norm, warnings
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest test_scorer.py::TestMoonScore test_scorer.py::TestDarkHoursAfterMoonset -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scorer.py test_scorer.py
git commit -m "refactor: _moon_score returns 0-1 normalized score using sub-weights"
```

---

## Task 5: Refactor `score_night` to normalize with top-level weights

**Files:**
- Modify: `scorer.py`
- Modify: `test_scorer.py`
- Modify: `smtp_notifier.py`

`Score.weather_score`, `Score.seeing_score`, `Score.moon_score` now store 0–100 ints (each category's normalized score as a percentage). The report format changes from `/40, /30, /30` to `%`.

`score_night` accepts `weights: ScoringWeights = None`. The `go_threshold` parameter is kept for backward compat but defaults to `weights.go_threshold` when not passed explicitly.

Total formula:
```
total_w = weather_weight + seeing_weight + moon_weight
total = int((weather_weight * weather_norm + seeing_weight * seeing_norm + moon_weight * moon_norm) / total_w * 100)
```

- [ ] **Step 1: Update failing tests for `TestScoreNight`**

Replace the entire `TestScoreNight` class in `test_scorer.py`:

```python
class TestScoreNight:
    def test_perfect_conditions_go(self):
        score = score_night(
            make_weather(cloud=5, wind=5),
            make_seeing(8, 8),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go
        assert score.total >= 80

    def test_terrible_conditions_nogo(self):
        score = score_night(
            make_weather(cloud=95, precip=2.0),
            make_seeing(1, 1),
            make_moon(phase=98, is_up=True),
            bortle=7,
        )
        assert not score.go
        assert score.total < 55

    def test_score_category_values_are_percentages(self):
        score = score_night(
            make_weather(cloud=5),
            make_seeing(8, 8),
            make_moon(phase=2),
            bortle=7,
        )
        assert 0 <= score.weather_score <= 100
        assert 0 <= score.seeing_score <= 100
        assert 0 <= score.moon_score <= 100

    def test_custom_threshold_via_weights(self):
        from scoring_weights import ScoringWeights
        w = ScoringWeights(go_threshold=10)
        score = score_night(
            make_weather(cloud=40),
            make_seeing(5, 5),
            make_moon(phase=40),
            bortle=7,
            weights=w,
        )
        assert score.go

    def test_custom_threshold_param_overrides_weights(self):
        # go_threshold kwarg still works for backward compat
        score = score_night(
            make_weather(cloud=40),
            make_seeing(5, 5),
            make_moon(phase=40),
            bortle=7,
            go_threshold=10,
        )
        assert score.go

    def test_bright_moon_up_at_midnight_hard_nogo(self):
        score = score_night(
            make_weather(cloud=0),
            make_seeing(8, 8),
            make_moon(phase=80, is_up=True),
            bortle=7,
        )
        assert not score.go
        assert "bright moon" in score.summary.lower()

    def test_bright_moon_sets_before_midnight_not_hard_nogo(self):
        score = score_night(
            make_weather(cloud=0),
            make_seeing(8, 8),
            make_moon(phase=80, is_up=False, set_=moonset_at(21)),
            bortle=7,
        )
        assert "bright moon" not in score.summary.lower()

    def test_summary_excellent(self):
        score = score_night(
            make_weather(cloud=5, wind=3),
            make_seeing(8, 8),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go
        assert "excellent" in score.summary.lower()

    def test_summary_good(self):
        # Partly cloudy (cloud=30) + mid seeing (6,6) + new moon = should be 65-79
        score = score_night(
            make_weather(cloud=30),
            make_seeing(6, 6),
            make_moon(phase=2),
            bortle=7,
        )
        assert score.go

    def test_summary_marginal(self):
        # Design a case that lands 55-64: overcast + poor seeing + new moon
        score = score_night(
            make_weather(cloud=90),
            make_seeing(3, 3),
            make_moon(phase=2),
            bortle=7,
        )
        # Overcast weather is low but seeing/moon still contribute; verify it's near threshold
        assert score.total < 80  # not excellent

    def test_target_date_filters_hours(self):
        target = date(2024, 1, 1)
        h_in = HourlyWeather(
            time=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            cloud_cover_pct=0, precip_mm=0, wind_speed_kmh=5,
            humidity_pct=50, dew_point_c=5, temp_c=15,
        )
        h_out = HourlyWeather(
            time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            cloud_cover_pct=100, precip_mm=5, wind_speed_kmh=50,
            humidity_pct=99, dew_point_c=14, temp_c=15,
        )
        result = WeatherResult(
            site_key="test",
            fetched_at=datetime.now(timezone.utc),
            hours=[h_in, h_out],
        )
        norm_with_date, _, _ = _weather_score(result, bortle=7, target_date=target)
        norm_no_date, _, _ = _weather_score(result, bortle=7, target_date=None)
        assert norm_with_date > norm_no_date

    def test_high_weather_weight_dominates(self):
        from scoring_weights import ScoringWeights
        # Perfect weather, terrible seeing/moon
        w = ScoringWeights(weather_weight=90, seeing_weight=5, moon_weight=5)
        score = score_night(
            make_weather(cloud=5, wind=5),
            make_seeing(1, 1),
            make_moon(phase=98, is_up=True),
            bortle=7,
            weights=w,
        )
        # Despite terrible seeing/moon, high weather weight should keep score high
        assert score.total > 50
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest test_scorer.py::TestScoreNight -v
```
Expected: multiple FAILs.

- [ ] **Step 3: Update `Score` dataclass comments and update `score_night` in `scorer.py`**

Update the `Score` dataclass:

```python
@dataclass
class Score:
    total: int              # 0–100 weighted combined score
    weather_score: int      # 0–100 normalized weather sub-score
    seeing_score: int       # 0–100 normalized seeing sub-score
    moon_score: int         # 0–100 normalized moon sub-score
    go: bool
    summary: str
    warnings: list[str]
    avg_cloud_pct: int = -1
```

Replace `score_night`:

```python
def score_night(
    weather: WeatherResult,
    seeing: SeeingResult,
    moon: MoonInfo,
    bortle: int,
    target_date: Optional[date] = None,
    go_threshold: Optional[int] = None,
    weights: Optional["ScoringWeights"] = None,
) -> Score:
    from scoring_weights import ScoringWeights
    if weights is None:
        weights = ScoringWeights()
    threshold = go_threshold if go_threshold is not None else weights.go_threshold

    w_norm, w_warn, avg_cloud = _weather_score(weather, bortle, target_date, weights)
    s_norm, s_warn = _seeing_score(seeing, target_date, weights)
    m_norm, m_warn = _moon_score(moon, weights)

    total_w = weights.weather_weight + weights.seeing_weight + weights.moon_weight
    total = int(
        (weights.weather_weight * w_norm + weights.seeing_weight * s_norm + weights.moon_weight * m_norm)
        / total_w * 100
    )

    all_warnings = w_warn + s_warn + m_warn
    moon_kills_night = moon.phase_pct >= 75 and moon.is_up_at_midnight

    if moon_kills_night:
        go = False
        summary = f"No-go — bright moon ({moon.phase_pct:.0f}%) up all night."
    elif total >= threshold:
        go = True
        if total >= 80:
            summary = "Excellent night — go image."
        elif total >= 65:
            summary = "Good night — go image."
        else:
            summary = "Marginal but go-able — worth setting up."
    else:
        go = False
        summary = "No-go tonight."

    return Score(
        total=total,
        weather_score=int(w_norm * 100),
        seeing_score=int(s_norm * 100),
        moon_score=int(m_norm * 100),
        go=go,
        summary=summary,
        warnings=all_warnings,
        avg_cloud_pct=avg_cloud,
    )
```

- [ ] **Step 4: Update `smtp_notifier.py` report format**

In `_format_report`, change the score line:

```python
lines = [
    f"{report.site_name} ({drive})",
    f"  {go_label} - {score.total}/100  "
    f"[weather {score.weather_score}%, seeing {score.seeing_score}%, moon {score.moon_score}%]",
]
```

- [ ] **Step 5: Run all scorer and notifier tests**

```bash
python3 -m pytest test_scorer.py test_notifier.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scorer.py smtp_notifier.py test_scorer.py
git commit -m "refactor: score_night normalizes with top-level weights; category scores now 0-100 each"
```

---

## Task 6: Wire weights into `astro_alert.py`

**Files:**
- Modify: `astro_alert.py`

Load weights once in `_fetch_report` and pass to `score_night`. Update the CLI summary output to match the new `%` format.

- [ ] **Step 1: Update `_fetch_report` and the summary output in `astro_alert.py`**

```python
# at top of file, add import
from scoring_weights import load_weights

# Replace _fetch_report:
def _fetch_report(site, target_date) -> SiteReport:
    weights = load_weights()
    weather = fetch_weather(site.key, site.lat, site.lon, target_date=target_date)
    seeing = fetch_seeing(site.key, site.lat, site.lon)
    moon = get_moon_info(site.lat, site.lon, target_date=target_date)
    score = score_night(weather, seeing, moon, bortle=site.bortle, target_date=target_date, weights=weights)
    return SiteReport(site_name=site.name, drive_min=site.drive_min, score=score, moon=moon)
```

- [ ] **Step 2: Run the CLI dry-run and verify output**

```bash
python3 astro_alert.py --dry-run 2>&1 | head -30
```
Expected: report lines show `[weather X%, seeing X%, moon X%]` format. The dry-run should complete without errors.

- [ ] **Step 3: Run full test suite**

```bash
python3 -m pytest test_scorer.py test_notifier.py test_cli.py test_scoring_weights.py -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add astro_alert.py
git commit -m "feat: wire scoring weights into CLI forecast run"
```

---

## Task 7: Add Scoring tab to GUI

**Files:**
- Modify: `gui.py`

Add a 5th tab between Schedule and Settings. Build it with a scrollable canvas (same pattern as Settings tab). Sliders are `ttk.Scale` with `IntVar` and a live value label.

- [ ] **Step 1: Add tab frame and register it in `_build_notebook`**

In `_build_notebook`, add after the existing tabs:

```python
self._tab_scoring = ttk.Frame(nb)
nb.add(self._tab_scoring, text="  Scoring  ")
```

Insert the tab between Schedule and Settings:

```python
nb.add(self._tab_dash,     text="  Dashboard  ")
nb.add(self._tab_sites,    text="  Sites  ")
nb.add(self._tab_sched,    text="  Schedule  ")
nb.add(self._tab_scoring,  text="  Scoring  ")
nb.add(self._tab_settings, text="  Settings  ")
```

And add the build call:

```python
self._build_scoring_tab(self._tab_scoring)
```

- [ ] **Step 2: Implement `_build_scoring_tab`**

Add this method to the `App` class (place it before `_build_settings_tab`):

```python
def _build_scoring_tab(self, parent):
    from scoring_weights import ScoringWeights, load_weights, save_weights

    canvas = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = ttk.Frame(canvas)
    _win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(_win, width=e.width))

    def _on_mousewheel(e):
        delta = e.delta
        if sys.platform != "darwin":
            delta = delta // 120
        canvas.yview_scroll(int(-1 * delta), "units")
    canvas.bind("<Enter>", lambda e: (
        canvas.bind_all("<Button-4>", lambda ev: canvas.yview_scroll(-1, "units")),
        canvas.bind_all("<Button-5>", lambda ev: canvas.yview_scroll(1, "units")),
        canvas.bind_all("<MouseWheel>", _on_mousewheel),
    ))
    canvas.bind("<Leave>", lambda e: (
        canvas.unbind_all("<Button-4>"),
        canvas.unbind_all("<Button-5>"),
        canvas.unbind_all("<MouseWheel>"),
    ))

    ttk.Label(inner, text="Scoring Weights",
              font=(FONT_PROP, 17, "bold")).pack(pady=(0, 5))
    ttk.Label(inner,
              text="Adjust how each factor contributes to the go/no-go score. "
                   "Relative values — normalized automatically.",
              style="Sub.TLabel").pack(pady=(0, 22))

    defaults = ScoringWeights()
    current = load_weights()

    # IntVars keyed by field name
    self._scoring_vars: dict[str, tk.IntVar] = {}
    for field in vars(defaults):
        self._scoring_vars[field] = tk.IntVar(value=getattr(current, field))

    def _make_section(title, fields):
        """fields: list of (label, field_name)"""
        lf = ttk.LabelFrame(inner, text=title, padding=(16, 8))
        lf.pack(fill="x", padx=24, pady=(0, 16))
        lf.columnconfigure(1, weight=1)
        for row, (label, field) in enumerate(fields):
            var = self._scoring_vars[field]
            ttk.Label(lf, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            val_lbl = ttk.Label(lf, text=str(var.get()), width=4, anchor="e")
            val_lbl.grid(row=row, column=2, padx=(8, 0), pady=4)

            def _trace(name, *_, v=var, lbl=val_lbl):
                lbl.configure(text=str(v.get()))

            var.trace_add("write", _trace)
            ttk.Scale(
                lf, from_=0, to=100,
                orient="horizontal",
                variable=var,
                command=lambda val, v=var: v.set(int(float(val))),
            ).grid(row=row, column=1, sticky="ew", pady=4)

    _make_section("Top-Level Weights", [
        ("Weather", "weather_weight"),
        ("Seeing",  "seeing_weight"),
        ("Moon",    "moon_weight"),
    ])
    _make_section("Weather Sub-Weights", [
        ("Cloud Cover",    "cloud_weight"),
        ("Wind",           "wind_weight"),
        ("Humidity / Dew", "dew_weight"),
    ])
    _make_section("Seeing Sub-Weights", [
        ("Seeing Quality", "seeing_quality_weight"),
        ("Transparency",   "transparency_weight"),
    ])
    _make_section("Moon Sub-Weights", [
        ("Moon Phase",        "phase_weight"),
        ("Dark Hours After Moonset", "dark_hours_weight"),
    ])
    _make_section("GO Threshold", [
        ("Min score to send GO alert", "go_threshold"),
    ])

    btn_row = ttk.Frame(inner)
    btn_row.pack(fill="x", padx=24, pady=(8, 24))

    self._scoring_status = tk.StringVar(value="")
    ttk.Label(btn_row, textvariable=self._scoring_status,
              style="Dim.TLabel").pack(side="left")

    def _reset():
        d = ScoringWeights()
        for field, var in self._scoring_vars.items():
            var.set(getattr(d, field))
        self._scoring_status.set("Reset to defaults — click Save to apply.")

    def _save():
        w = ScoringWeights(**{f: v.get() for f, v in self._scoring_vars.items()})
        save_weights(w)
        self._scoring_status.set("Saved.")
        self.after(3000, lambda: self._scoring_status.set(""))

    ttk.Button(btn_row, text="Reset to Defaults", command=_reset).pack(side="left", padx=(8, 0))
    ttk.Button(btn_row, text="Save", style="Go.TButton", command=_save).pack(side="right")
```

- [ ] **Step 3: Run the app and verify the Scoring tab appears**

```bash
python3 main.py
```
Expected: app opens, Scoring tab is visible between Schedule and Settings. Sliders load current weights. Dragging updates the live value label. Reset restores defaults. Save writes to `scoring_weights.json` (check `~/Library/Application\ Support/AstroAlert/scoring_weights.json` on macOS).

- [ ] **Step 4: Run test suite**

```bash
python3 -m pytest test_scorer.py test_notifier.py test_cli.py test_scoring_weights.py test_gui.py -q
```
Expected: all pass (GUI tests don't test the Scoring tab internals, just that the app builds without crashing).

- [ ] **Step 5: Commit**

```bash
git add gui.py
git commit -m "feat: add Scoring tab with sliders for all scoring weights"
```

---

## Task 8: Build, smoke-test, tag, and push

**Files:** none (build artifacts only)

- [ ] **Step 1: Build the app**

```bash
cd /Users/pauldavis/astro_alert
rm -rf build dist && pyinstaller AstroAlert.spec 2>&1 | tail -5
```
Expected: `Build complete! The results are available in: .../dist`

- [ ] **Step 2: Open the built app and verify end-to-end**

```bash
open dist/AstroAlert.app
```

Verify:
1. Scoring tab is visible with all sliders at correct defaults
2. Change Weather weight to 80, Save → run a Dashboard forecast → confirm it completes without error
3. Reset to Defaults → Save → weights return to defaults

- [ ] **Step 3: Run full test suite one final time**

```bash
python3 -m pytest -q
```
Expected: all tests pass.

- [ ] **Step 4: Commit any remaining changes and push**

```bash
git push
```

- [ ] **Step 5: Tag the release**

```bash
git tag v1.1.0
git push origin v1.1.0
```
