# User-Configurable Scoring Weights

**Date:** 2026-04-26
**Status:** Approved

## Overview

Allow users to adjust the weights used by the go/no-go scorer via a new Scoring tab in the GUI. All weights are global (apply to all sites), persist between sessions, and default to values that reproduce today's hardcoded behavior exactly.

## Data Model

New module `scoring_weights.py` owns a `ScoringWeights` dataclass with 11 fields:

| Field | Default | Meaning |
|---|---|---|
| `weather_weight` | 40 | Top-level weather importance |
| `seeing_weight` | 30 | Top-level seeing importance |
| `moon_weight` | 30 | Top-level moon importance |
| `go_threshold` | 55 | Minimum score to call a night GO |
| `cloud_weight` | 70 | Cloud cover share within weather |
| `wind_weight` | 20 | Wind share within weather |
| `dew_weight` | 10 | Humidity/dew share within weather |
| `seeing_quality_weight` | 50 | Seeing quality share within seeing |
| `transparency_weight` | 50 | Transparency share within seeing |
| `phase_weight` | 70 | Moon phase share within moon |
| `dark_hours_weight` | 30 | Dark hours after moonset share within moon |

Saved to `DATA_DIR/scoring_weights.json` via `load_weights()` / `save_weights()`. Missing file → `ScoringWeights()` defaults.

## Scoring Logic Changes

`score_night()` gains `weights: ScoringWeights = None` (defaults to `ScoringWeights()` — no change to existing callers).

Each category is first normalized to 0–1, then combined:

```
total = (w_weather × weather_norm + w_seeing × seeing_norm + w_moon × moon_norm)
        ──────────────────────────────────────────────────────────────────────── × 100
                         w_weather + w_seeing + w_moon
```

The same normalization applies within each category:

**Weather sub-score (0–1):**
- `cloud_raw`: tier-based (clear=1.0, mostly clear=0.8, partly=0.45, mostly cloudy=0.2, overcast=0.0)
- `wind_raw`: calm (<20 km/h)=1.0, moderate (20–30 km/h)=0.5, high (>30 km/h)=0.0
- `dew_raw`: gap≥4°C=1.0, gap 2–4°C=0.5, gap<2°C=0.0; humidity>90% applies same scale
- Combined: `(cloud_weight×cloud_raw + wind_weight×wind_raw + dew_weight×dew_raw) / (cloud_weight+wind_weight+dew_weight)`

**Seeing sub-score (0–1):**
- `seeing_raw` = avg_seeing / 8
- `transparency_raw` = avg_transparency / 8
- Combined: `(seeing_quality_weight×seeing_raw + transparency_weight×transparency_raw) / (seeing_quality_weight+transparency_weight)`

**Moon sub-score (0–1):**
- `phase_raw`: phase-tier score normalized to 0–1 (new moon=1.0 → full moon=0.0)
- `dark_hours_raw` = dark_hours_after_moonset / 8 (0 if moon sets after imaging window)
- Combined: `(phase_weight×phase_raw + dark_hours_weight×dark_hours_raw) / (phase_weight+dark_hours_weight)`

The hard NO-GO cutoff (bright moon ≥75% up at midnight) is **not weight-configurable** — it remains a hard override.

`go_threshold` moves from `score_night()`'s default parameter to `weights.go_threshold`.

`score_night()` also passes `weights` down to `_weather_score`, `_seeing_score`, `_moon_score`.

## Persistence

`scoring_weights.py` exports:
- `load_weights() -> ScoringWeights` — reads `DATA_DIR/scoring_weights.json`; returns defaults if missing or malformed
- `save_weights(weights: ScoringWeights) -> None` — writes JSON atomically

## GUI — Scoring Tab

New fifth tab **Scoring** added between Schedule and Settings in `gui.py`.

Layout (scrollable frame, same pattern as Settings tab):

```
┌─ Top-Level Weights ──────────────────────────────┐
│  Weather      [────────●──────] 40               │
│  Seeing       [──────●────────] 30               │
│  Moon         [──────●────────] 30               │
│  (Relative values — normalized automatically)    │
└──────────────────────────────────────────────────┘
┌─ Weather ────────────────────────────────────────┐
│  Cloud Cover  [──────────────●] 70               │
│  Wind         [─────●─────────] 20               │
│  Humidity/Dew [──●────────────] 10               │
└──────────────────────────────────────────────────┘
┌─ Seeing ─────────────────────────────────────────┐
│  Seeing Quality  [───────●────] 50               │
│  Transparency    [───────●────] 50               │
└──────────────────────────────────────────────────┘
┌─ Moon ───────────────────────────────────────────┐
│  Moon Phase      [──────────●─] 70               │
│  Dark Hours      [────●───────] 30               │
└──────────────────────────────────────────────────┘
┌─ GO Threshold ───────────────────────────────────┐
│  Min score to send GO alert                      │
│  [──────────●──────────────────] 55              │
└──────────────────────────────────────────────────┘
[Reset to Defaults]                        [Save]
```

Each row: `ttk.Label` (left) + `ttk.Scale` 0–100 + `ttk.Label` showing live integer value (right). Value label updates on every slider move via `variable.trace_add`.

**Save** — calls `save_weights()`, shows a brief "Saved." status message.
**Reset to Defaults** — resets all `IntVar`s to their defaults, does not auto-save (user must still click Save).

Weights are loaded from `scoring_weights.json` when the tab is built. The next forecast run after saving picks up the new weights automatically (loaded fresh in `cmd_run`).

## Files Changed

| File | Change |
|---|---|
| `scoring_weights.py` | New — dataclass, load/save |
| `scorer.py` | Accept `ScoringWeights`; refactor sub-scores to use weights |
| `gui.py` | Add Scoring tab |
| `astro_alert.py` | Load weights in `cmd_run`, pass to `score_night` |
| `test_scoring_weights.py` | New — load/save, defaults, normalization |
| `test_scorer.py` | Update to pass weights; verify weighted outcomes |

## Testing

- `test_scoring_weights.py`: load with missing file returns defaults; round-trip save/load; malformed JSON returns defaults
- `test_scorer.py`: passing `ScoringWeights()` defaults produces same scores as before (regression guard); extreme weights (e.g. moon_weight=100, others=0) produce expected results; go_threshold respected from weights
- Existing tests pass without modification (default weights = current behavior)
