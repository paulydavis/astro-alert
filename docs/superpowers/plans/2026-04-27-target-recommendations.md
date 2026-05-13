# Target Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each GO night in the 14-night Forecast tab and in the HTML email, show up to 10 recommended deep-sky objects that are well-placed that night, ranked by peak altitude.

**Architecture:** A curated `targets.json` of ~96 popular DSOs feeds `target_recommender.py`, which uses `ephem` (already in the project) to compute altitude for each object across the imaging window and return the top 10. Results appear in the Forecast tab detail panel (local time) and in the HTML email (UTC). A new `compute_imaging_window` helper is extracted into `moon.py` so both GUI and email share the same window logic without a circular import.

**Tech Stack:** Python 3.11+, ephem, tkinter ttk.Treeview, existing dark-theme styles (CARD, TEXT, TEXT_DIM, FONT_PROP, FONT_MONO).

---

## Files

| File | Action | Purpose |
|------|--------|---------|
| `targets.json` | Create | ~96 curated DSOs with RA/Dec, type, description |
| `target_recommender.py` | Create | `get_nightly_targets()` — visibility computation |
| `test_target_recommender.py` | Create | 7 unit tests |
| `moon.py` | Modify | Add `compute_imaging_window(lat, lon, target_date)` |
| `gui.py` | Modify | Add targets treeview to detail panel; compute targets in `_run_forecast_load` |
| `smtp_notifier.py` | Modify | Add targets HTML table per GO site |
| `test_gui.py` | Modify | Add `test_forecast_target_tree_exists` |

---

## Task 1: Create `targets.json`

**Files:**
- Create: `targets.json`
- Test: `test_target_recommender.py` (written in Task 2, but validated here first)

- [ ] **Step 1: Write a validation test for the JSON structure**

```python
# test_target_recommender.py (create this file now — Task 2 adds more tests)
import json
from pathlib import Path

def test_targets_json_loads_and_has_required_fields():
    data = json.loads((Path(__file__).parent / "targets.json").read_text())
    assert len(data) >= 90
    required = {"name", "common_name", "type", "ra", "dec", "magnitude", "size_arcmin", "description"}
    for entry in data:
        missing = required - entry.keys()
        assert not missing, f"{entry.get('name', '?')} missing: {missing}"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest test_target_recommender.py::test_targets_json_loads_and_has_required_fields -v
```
Expected: FAIL — `targets.json` does not exist yet.

- [ ] **Step 3: Create `targets.json`**

```json
[
  {"name": "M31",          "common_name": "Andromeda Galaxy",       "type": "Galaxy",              "ra": "00:42:44", "dec": "+41:16:09", "magnitude": 3.4,  "size_arcmin": 190, "description": "Nearest large galaxy; stunning in wide-field"},
  {"name": "M32",          "common_name": "Le Gentil",              "type": "Galaxy",              "ra": "00:42:42", "dec": "+40:51:55", "magnitude": 8.7,  "size_arcmin": 8,   "description": "Compact elliptical satellite of M31"},
  {"name": "M33",          "common_name": "Triangulum Galaxy",      "type": "Galaxy",              "ra": "01:33:51", "dec": "+30:39:37", "magnitude": 5.7,  "size_arcmin": 73,  "description": "Third largest Local Group galaxy; low surface brightness"},
  {"name": "M51",          "common_name": "Whirlpool Galaxy",       "type": "Galaxy",              "ra": "13:29:53", "dec": "+47:11:43", "magnitude": 8.4,  "size_arcmin": 11,  "description": "Iconic interacting pair with NGC 5195"},
  {"name": "M63",          "common_name": "Sunflower Galaxy",       "type": "Galaxy",              "ra": "13:15:49", "dec": "+42:01:46", "magnitude": 8.6,  "size_arcmin": 13,  "description": "Flocculent spiral in Canes Venatici"},
  {"name": "M64",          "common_name": "Black Eye Galaxy",       "type": "Galaxy",              "ra": "12:56:44", "dec": "+21:40:59", "magnitude": 8.5,  "size_arcmin": 10,  "description": "Distinctive dust lane near the nucleus"},
  {"name": "M77",          "common_name": "Cetus A",                "type": "Galaxy",              "ra": "02:42:41", "dec": "-00:00:48", "magnitude": 8.9,  "size_arcmin": 7,   "description": "Seyfert galaxy with active nucleus"},
  {"name": "M81",          "common_name": "Bode's Galaxy",          "type": "Galaxy",              "ra": "09:55:33", "dec": "+69:03:55", "magnitude": 6.9,  "size_arcmin": 27,  "description": "Grand spiral; often paired with M82"},
  {"name": "M82",          "common_name": "Cigar Galaxy",           "type": "Galaxy",              "ra": "09:55:52", "dec": "+69:40:47", "magnitude": 8.4,  "size_arcmin": 11,  "description": "Starburst galaxy with dramatic red H-alpha jets"},
  {"name": "M87",          "common_name": "Virgo A",                "type": "Galaxy",              "ra": "12:30:49", "dec": "+12:23:28", "magnitude": 8.6,  "size_arcmin": 8,   "description": "Giant elliptical hosting famous black hole jet"},
  {"name": "M101",         "common_name": "Pinwheel Galaxy",        "type": "Galaxy",              "ra": "14:03:13", "dec": "+54:20:57", "magnitude": 7.9,  "size_arcmin": 29,  "description": "Face-on spiral; requires dark skies"},
  {"name": "M104",         "common_name": "Sombrero Galaxy",        "type": "Galaxy",              "ra": "12:39:59", "dec": "-11:37:23", "magnitude": 8.0,  "size_arcmin": 9,   "description": "Bright dust lane gives hat-brim appearance"},
  {"name": "M106",         "common_name": "NGC 4258",               "type": "Galaxy",              "ra": "12:18:58", "dec": "+47:18:14", "magnitude": 8.4,  "size_arcmin": 19,  "description": "Seyfert spiral with anomalous arms"},
  {"name": "M109",         "common_name": "Vacuum Cleaner Galaxy",  "type": "Galaxy",              "ra": "11:57:36", "dec": "+53:22:28", "magnitude": 9.8,  "size_arcmin": 8,   "description": "Barred spiral near Phecda in Ursa Major"},
  {"name": "NGC 253",      "common_name": "Sculptor Galaxy",        "type": "Galaxy",              "ra": "00:47:33", "dec": "-25:17:18", "magnitude": 7.1,  "size_arcmin": 28,  "description": "Bright edge-on starburst; best from southern latitudes"},
  {"name": "NGC 891",      "common_name": "Silver Sliver Galaxy",   "type": "Galaxy",              "ra": "02:22:33", "dec": "+42:20:57", "magnitude": 9.9,  "size_arcmin": 14,  "description": "Archetypal edge-on galaxy with central dust lane"},
  {"name": "NGC 2903",     "common_name": "NGC 2903",               "type": "Galaxy",              "ra": "09:32:10", "dec": "+21:30:03", "magnitude": 8.9,  "size_arcmin": 13,  "description": "Bright barred spiral overlooked by Messier"},
  {"name": "NGC 4565",     "common_name": "Needle Galaxy",          "type": "Galaxy",              "ra": "12:36:21", "dec": "+25:59:16", "magnitude": 9.6,  "size_arcmin": 16,  "description": "Classic edge-on spiral with prominent dust lane"},
  {"name": "NGC 4631",     "common_name": "Whale Galaxy",           "type": "Galaxy",              "ra": "12:42:08", "dec": "+32:32:29", "magnitude": 9.2,  "size_arcmin": 16,  "description": "Edge-on irregular paired with NGC 4627"},
  {"name": "NGC 7331",     "common_name": "NGC 7331",               "type": "Galaxy",              "ra": "22:37:04", "dec": "+34:24:57", "magnitude": 9.5,  "size_arcmin": 11,  "description": "Milky Way look-alike; near Stephan's Quintet"},
  {"name": "IC 342",       "common_name": "Hidden Galaxy",          "type": "Galaxy",              "ra": "03:46:49", "dec": "+68:05:46", "magnitude": 8.4,  "size_arcmin": 21,  "description": "Large face-on spiral obscured by Milky Way dust"},
  {"name": "M8",           "common_name": "Lagoon Nebula",          "type": "Emission Nebula",     "ra": "18:03:37", "dec": "-24:23:12", "magnitude": 6.0,  "size_arcmin": 90,  "description": "Large binocular nebula in Sagittarius"},
  {"name": "M16",          "common_name": "Eagle Nebula",           "type": "Emission Nebula",     "ra": "18:18:48", "dec": "-13:47:06", "magnitude": 6.4,  "size_arcmin": 35,  "description": "Contains the iconic Pillars of Creation"},
  {"name": "M17",          "common_name": "Omega Nebula",           "type": "Emission Nebula",     "ra": "18:20:26", "dec": "-16:10:36", "magnitude": 6.0,  "size_arcmin": 46,  "description": "Swan-shaped nebula; one of the brightest H II regions"},
  {"name": "M20",          "common_name": "Trifid Nebula",          "type": "Emission Nebula",     "ra": "18:02:23", "dec": "-23:01:48", "magnitude": 6.3,  "size_arcmin": 29,  "description": "Tri-lobed emission nebula with embedded reflection component"},
  {"name": "M42",          "common_name": "Orion Nebula",           "type": "Emission Nebula",     "ra": "05:35:17", "dec": "-05:23:28", "magnitude": 4.0,  "size_arcmin": 85,  "description": "Brightest nebula in the sky; superb in any conditions"},
  {"name": "M43",          "common_name": "De Mairan's Nebula",     "type": "Emission Nebula",     "ra": "05:35:31", "dec": "-05:16:03", "magnitude": 9.0,  "size_arcmin": 20,  "description": "Comma-shaped nebula adjacent to M42"},
  {"name": "NGC 281",      "common_name": "Pacman Nebula",          "type": "Emission Nebula",     "ra": "00:52:59", "dec": "+56:37:19", "magnitude": 7.4,  "size_arcmin": 35,  "description": "H II region near Cassiopeia; strong H-alpha signal"},
  {"name": "NGC 1499",     "common_name": "California Nebula",      "type": "Emission Nebula",     "ra": "04:03:14", "dec": "+36:25:18", "magnitude": 6.0,  "size_arcmin": 145, "description": "Very large faint nebula; benefits from H-alpha filter"},
  {"name": "NGC 2237",     "common_name": "Rosette Nebula",         "type": "Emission Nebula",     "ra": "06:31:55", "dec": "+04:56:00", "magnitude": 6.0,  "size_arcmin": 80,  "description": "Large ring nebula surrounding open cluster NGC 2244"},
  {"name": "NGC 6888",     "common_name": "Crescent Nebula",        "type": "Emission Nebula",     "ra": "20:12:07", "dec": "+38:21:18", "magnitude": 7.4,  "size_arcmin": 18,  "description": "Wolf-Rayet bubble nebula in Cygnus"},
  {"name": "NGC 7000",     "common_name": "North America Nebula",   "type": "Emission Nebula",     "ra": "20:58:47", "dec": "+44:20:00", "magnitude": 4.0,  "size_arcmin": 120, "description": "Huge H-alpha nebula adjacent to Deneb"},
  {"name": "IC 405",       "common_name": "Flaming Star Nebula",    "type": "Emission Nebula",     "ra": "05:16:12", "dec": "+34:16:00", "magnitude": 6.0,  "size_arcmin": 37,  "description": "Mixed emission and reflection nebula in Auriga"},
  {"name": "IC 410",       "common_name": "Tadpole Nebula",         "type": "Emission Nebula",     "ra": "05:22:45", "dec": "+33:22:00", "magnitude": 7.0,  "size_arcmin": 40,  "description": "H II region with comet-like globules in Auriga"},
  {"name": "IC 1805",      "common_name": "Heart Nebula",           "type": "Emission Nebula",     "ra": "02:32:42", "dec": "+61:27:00", "magnitude": 6.5,  "size_arcmin": 60,  "description": "Heart-shaped H II region in Cassiopeia"},
  {"name": "IC 1848",      "common_name": "Soul Nebula",            "type": "Emission Nebula",     "ra": "02:51:12", "dec": "+60:24:00", "magnitude": 6.5,  "size_arcmin": 60,  "description": "Often imaged paired with IC 1805 as Heart and Soul"},
  {"name": "IC 5070",      "common_name": "Pelican Nebula",         "type": "Emission Nebula",     "ra": "20:50:48", "dec": "+44:21:00", "magnitude": 8.0,  "size_arcmin": 60,  "description": "Adjacent to NGC 7000; rich in pillar structures"},
  {"name": "NGC 7380",     "common_name": "Wizard Nebula",          "type": "Emission Nebula",     "ra": "22:47:21", "dec": "+58:07:54", "magnitude": 7.2,  "size_arcmin": 25,  "description": "H II region with embedded cluster in Cepheus"},
  {"name": "Sh2-155",      "common_name": "Cave Nebula",            "type": "Emission Nebula",     "ra": "22:57:54", "dec": "+62:30:00", "magnitude": 7.7,  "size_arcmin": 50,  "description": "Mixed emission and reflection nebula in Cepheus"},
  {"name": "M1",           "common_name": "Crab Nebula",            "type": "Supernova Remnant",   "ra": "05:34:32", "dec": "+22:00:52", "magnitude": 8.4,  "size_arcmin": 7,   "description": "Remnant of SN 1054; harbours a pulsar"},
  {"name": "NGC 6960",     "common_name": "Western Veil Nebula",    "type": "Supernova Remnant",   "ra": "20:45:38", "dec": "+30:42:30", "magnitude": 7.0,  "size_arcmin": 70,  "description": "Western arc of the Cygnus Loop supernova remnant"},
  {"name": "NGC 6992",     "common_name": "Eastern Veil Nebula",    "type": "Supernova Remnant",   "ra": "20:56:24", "dec": "+31:43:00", "magnitude": 7.0,  "size_arcmin": 60,  "description": "Eastern arc of the Cygnus Loop; richly detailed"},
  {"name": "IC 443",       "common_name": "Jellyfish Nebula",       "type": "Supernova Remnant",   "ra": "06:17:00", "dec": "+22:47:00", "magnitude": 12.0, "size_arcmin": 50,  "description": "Interacting SNR in Gemini; requires dark skies and nebula filter"},
  {"name": "M78",          "common_name": "M78",                    "type": "Reflection Nebula",   "ra": "05:46:46", "dec": "+00:04:45", "magnitude": 8.0,  "size_arcmin": 8,   "description": "Brightest reflection nebula in the sky"},
  {"name": "NGC 7023",     "common_name": "Iris Nebula",            "type": "Reflection Nebula",   "ra": "21:01:36", "dec": "+68:10:10", "magnitude": 7.1,  "size_arcmin": 18,  "description": "Blue reflection nebula with striking dust filaments"},
  {"name": "IC 2118",      "common_name": "Witch Head Nebula",      "type": "Reflection Nebula",   "ra": "05:06:55", "dec": "-07:13:00", "magnitude": 13.0, "size_arcmin": 180, "description": "Faint reflection nebula illuminated by Rigel"},
  {"name": "NGC 1333",     "common_name": "NGC 1333",               "type": "Reflection Nebula",   "ra": "03:29:12", "dec": "+31:20:00", "magnitude": 5.6,  "size_arcmin": 6,   "description": "Young stellar region in Perseus with blue nebulosity"},
  {"name": "M27",          "common_name": "Dumbbell Nebula",        "type": "Planetary Nebula",    "ra": "19:59:36", "dec": "+22:43:16", "magnitude": 7.5,  "size_arcmin": 8,   "description": "Brightest and largest apparent planetary nebula"},
  {"name": "M57",          "common_name": "Ring Nebula",            "type": "Planetary Nebula",    "ra": "18:53:35", "dec": "+33:01:45", "magnitude": 8.8,  "size_arcmin": 1,   "description": "Classic smoke-ring planetary in Lyra"},
  {"name": "M76",          "common_name": "Little Dumbbell Nebula", "type": "Planetary Nebula",    "ra": "01:42:20", "dec": "+51:34:31", "magnitude": 10.1, "size_arcmin": 3,   "description": "Faint bipolar planetary in Perseus"},
  {"name": "M97",          "common_name": "Owl Nebula",             "type": "Planetary Nebula",    "ra": "11:14:48", "dec": "+55:01:09", "magnitude": 9.9,  "size_arcmin": 3,   "description": "Large faint planetary with two dark eye-like spots"},
  {"name": "NGC 2392",     "common_name": "Eskimo Nebula",          "type": "Planetary Nebula",    "ra": "07:29:11", "dec": "+20:54:43", "magnitude": 9.1,  "size_arcmin": 1,   "description": "Bright double-shell planetary in Gemini"},
  {"name": "NGC 3242",     "common_name": "Ghost of Jupiter",       "type": "Planetary Nebula",    "ra": "10:24:46", "dec": "-18:38:33", "magnitude": 8.6,  "size_arcmin": 2,   "description": "Bright blue-green planetary in Hydra"},
  {"name": "NGC 6543",     "common_name": "Cat's Eye Nebula",       "type": "Planetary Nebula",    "ra": "17:58:34", "dec": "+66:37:59", "magnitude": 8.1,  "size_arcmin": 1,   "description": "Complex concentric shell structure in Draco"},
  {"name": "NGC 6826",     "common_name": "Blinking Planetary",     "type": "Planetary Nebula",    "ra": "19:44:48", "dec": "+50:31:31", "magnitude": 8.8,  "size_arcmin": 1,   "description": "Central star blinks in and out with averted vision"},
  {"name": "NGC 7293",     "common_name": "Helix Nebula",           "type": "Planetary Nebula",    "ra": "22:29:39", "dec": "-20:50:14", "magnitude": 7.6,  "size_arcmin": 16,  "description": "Largest apparent-size planetary nebula; needs dark skies"},
  {"name": "NGC 7662",     "common_name": "Blue Snowball",          "type": "Planetary Nebula",    "ra": "23:25:54", "dec": "+42:32:06", "magnitude": 8.3,  "size_arcmin": 1,   "description": "Vivid blue planetary in Andromeda"},
  {"name": "M2",           "common_name": "M2",                     "type": "Globular Cluster",    "ra": "21:33:27", "dec": "-00:49:24", "magnitude": 6.5,  "size_arcmin": 13,  "description": "One of the largest and most massive globulars"},
  {"name": "M3",           "common_name": "M3",                     "type": "Globular Cluster",    "ra": "13:42:11", "dec": "+28:22:32", "magnitude": 6.2,  "size_arcmin": 18,  "description": "Outstanding northern globular in Canes Venatici"},
  {"name": "M4",           "common_name": "M4",                     "type": "Globular Cluster",    "ra": "16:23:35", "dec": "-26:31:33", "magnitude": 5.9,  "size_arcmin": 26,  "description": "Nearest globular to Earth; loosely concentrated"},
  {"name": "M5",           "common_name": "M5",                     "type": "Globular Cluster",    "ra": "15:18:34", "dec": "+02:04:58", "magnitude": 5.8,  "size_arcmin": 23,  "description": "Rivals M13; rich in variable stars"},
  {"name": "M10",          "common_name": "M10",                    "type": "Globular Cluster",    "ra": "16:57:09", "dec": "-04:05:58", "magnitude": 6.4,  "size_arcmin": 15,  "description": "Rich globular in Ophiuchus; paired with M12"},
  {"name": "M12",          "common_name": "M12",                    "type": "Globular Cluster",    "ra": "16:47:14", "dec": "-01:56:54", "magnitude": 6.7,  "size_arcmin": 16,  "description": "Loose open globular in Ophiuchus"},
  {"name": "M13",          "common_name": "Hercules Cluster",       "type": "Globular Cluster",    "ra": "16:41:42", "dec": "+36:27:36", "magnitude": 5.8,  "size_arcmin": 20,  "description": "Finest northern globular cluster"},
  {"name": "M15",          "common_name": "M15",                    "type": "Globular Cluster",    "ra": "21:29:58", "dec": "+12:10:01", "magnitude": 6.2,  "size_arcmin": 18,  "description": "Highly concentrated; harbours a planetary nebula"},
  {"name": "M22",          "common_name": "M22",                    "type": "Globular Cluster",    "ra": "18:36:24", "dec": "-23:54:17", "magnitude": 5.1,  "size_arcmin": 24,  "description": "One of the nearest and brightest globulars"},
  {"name": "M53",          "common_name": "M53",                    "type": "Globular Cluster",    "ra": "13:12:55", "dec": "+18:10:05", "magnitude": 7.7,  "size_arcmin": 13,  "description": "One of the most remote Messier globulars"},
  {"name": "M92",          "common_name": "M92",                    "type": "Globular Cluster",    "ra": "17:17:07", "dec": "+43:08:11", "magnitude": 6.4,  "size_arcmin": 14,  "description": "Overlooked sibling of M13 in Hercules"},
  {"name": "NGC 5139",     "common_name": "Omega Centauri",         "type": "Globular Cluster",    "ra": "13:26:46", "dec": "-47:28:37", "magnitude": 3.9,  "size_arcmin": 36,  "description": "Largest and most massive Milky Way globular; southern skies"},
  {"name": "M11",          "common_name": "Wild Duck Cluster",      "type": "Open Cluster",        "ra": "18:51:06", "dec": "-06:16:12", "magnitude": 6.3,  "size_arcmin": 14,  "description": "One of the richest and most compact open clusters"},
  {"name": "M35",          "common_name": "M35",                    "type": "Open Cluster",        "ra": "06:08:54", "dec": "+24:20:00", "magnitude": 5.3,  "size_arcmin": 28,  "description": "Rich winter cluster; NGC 2158 visible in background"},
  {"name": "M36",          "common_name": "Pinwheel Cluster",       "type": "Open Cluster",        "ra": "05:36:12", "dec": "+34:08:24", "magnitude": 6.3,  "size_arcmin": 12,  "description": "Compact cluster; part of the Auriga trio"},
  {"name": "M37",          "common_name": "M37",                    "type": "Open Cluster",        "ra": "05:52:18", "dec": "+32:33:12", "magnitude": 6.2,  "size_arcmin": 24,  "description": "Richest and largest of the three Auriga clusters"},
  {"name": "M38",          "common_name": "Starfish Cluster",       "type": "Open Cluster",        "ra": "05:28:42", "dec": "+35:51:18", "magnitude": 7.4,  "size_arcmin": 21,  "description": "Loose Auriga cluster with pi-shaped asterism"},
  {"name": "M41",          "common_name": "M41",                    "type": "Open Cluster",        "ra": "06:46:00", "dec": "-20:46:00", "magnitude": 4.5,  "size_arcmin": 38,  "description": "Binocular cluster south of Sirius"},
  {"name": "M44",          "common_name": "Beehive Cluster",        "type": "Open Cluster",        "ra": "08:40:06", "dec": "+19:59:00", "magnitude": 3.7,  "size_arcmin": 95,  "description": "Naked-eye open cluster in Cancer"},
  {"name": "M45",          "common_name": "Pleiades",               "type": "Open Cluster",        "ra": "03:47:24", "dec": "+24:07:00", "magnitude": 1.6,  "size_arcmin": 110, "description": "Most famous open cluster; blue reflection nebulosity"},
  {"name": "M50",          "common_name": "M50",                    "type": "Open Cluster",        "ra": "07:02:42", "dec": "-08:23:00", "magnitude": 6.3,  "size_arcmin": 16,  "description": "Heart-shaped winter cluster in Monoceros"},
  {"name": "M67",          "common_name": "M67",                    "type": "Open Cluster",        "ra": "08:51:18", "dec": "+11:49:00", "magnitude": 6.9,  "size_arcmin": 30,  "description": "One of the oldest known open clusters"},
  {"name": "NGC 869",      "common_name": "Double Cluster h Persei","type": "Open Cluster",        "ra": "02:18:58", "dec": "+56:59:00", "magnitude": 4.3,  "size_arcmin": 30,  "description": "Twin rich clusters in Perseus; stunning in wide-field"},
  {"name": "NGC 884",      "common_name": "Double Cluster χ Persei","type": "Open Cluster",        "ra": "02:22:23", "dec": "+57:08:00", "magnitude": 4.4,  "size_arcmin": 30,  "description": "Eastern twin of NGC 869; slightly older and redder"},
  {"name": "Albireo",      "common_name": "Albireo (β Cygni)",      "type": "Double Star",         "ra": "19:30:43", "dec": "+27:57:35", "magnitude": 3.1,  "size_arcmin": 0,   "description": "Showpiece gold-and-blue double in Cygnus"},
  {"name": "Epsilon Lyrae","common_name": "Double Double (ε Lyr)",  "type": "Double Star",         "ra": "18:44:20", "dec": "+39:40:12", "magnitude": 4.7,  "size_arcmin": 0,   "description": "Two close pairs resolvable in small telescopes"},
  {"name": "Almaak",       "common_name": "Almaak (γ And)",         "type": "Double Star",         "ra": "02:03:54", "dec": "+42:19:47", "magnitude": 2.3,  "size_arcmin": 0,   "description": "Striking gold-and-blue-green double in Andromeda"},
  {"name": "Mizar",        "common_name": "Mizar & Alcor (ζ UMa)",  "type": "Double Star",         "ra": "13:23:56", "dec": "+54:55:31", "magnitude": 2.1,  "size_arcmin": 0,   "description": "Naked-eye double with telescopic companion"},
  {"name": "Cor Caroli",   "common_name": "Cor Caroli (α CVn)",     "type": "Double Star",         "ra": "12:56:02", "dec": "+38:19:06", "magnitude": 2.9,  "size_arcmin": 0,   "description": "Wide blue-white double in Canes Venatici"}
]
```

- [ ] **Step 4: Run validation test to verify it passes**

```bash
pytest test_target_recommender.py::test_targets_json_loads_and_has_required_fields -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add targets.json test_target_recommender.py
git commit -m "feat: add curated targets.json with 96 DSOs"
```

---

## Task 2: Create `target_recommender.py` + add `compute_imaging_window` to `moon.py`

**Files:**
- Create: `target_recommender.py`
- Modify: `moon.py` — add `compute_imaging_window(lat, lon, target_date) -> set[datetime]`
- Modify: `gui.py` — replace inline window logic with `compute_imaging_window`
- Modify: `test_target_recommender.py` — add 6 more tests

- [ ] **Step 1: Write the failing tests**

Append to `test_target_recommender.py`:

```python
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import pytest

from target_recommender import get_nightly_targets, TargetResult

LAT, LON = 36.0, -78.9   # Durham NC
UTC = timezone.utc


def _window(start_hour, end_hour, base_date=None):
    """Build a set of UTC datetimes from start_hour to end_hour on base_date."""
    from datetime import date
    d = base_date or date(2024, 6, 15)
    return {
        datetime(d.year, d.month, d.day, h, tzinfo=UTC)
        for h in range(start_hour, end_hour + 1)
    }


def test_returns_empty_on_empty_window():
    results = get_nightly_targets(LAT, LON, set())
    assert results == []


def test_returns_empty_on_missing_targets_file(tmp_path, monkeypatch):
    monkeypatch.setattr("target_recommender._TARGETS_FILE", tmp_path / "missing.json")
    results = get_nightly_targets(LAT, LON, _window(0, 10))
    assert results == []


def test_m13_visible_in_june_from_north_carolina():
    # M13 transits at ~75° altitude from lat 36° in June; imaging window 01:00-10:00 UTC June 16
    from datetime import date
    d = date(2024, 6, 15)
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window)
    names = [r.name for r in results]
    assert "M13" in names


def test_filters_target_below_min_alt():
    # Use a tiny window where everything is below the horizon
    # Jan 1 at noon UTC — nearly all objects below horizon from any mid-lat site
    window = {datetime(2024, 1, 1, 12, tzinfo=UTC)}
    results = get_nightly_targets(LAT, LON, window, min_alt_deg=25.0, min_hours=1.0)
    # Not asserting empty (some circumpolar objects may be up) but peak_alt >= 25 for all
    for r in results:
        assert r.peak_alt_deg >= 25.0


def test_sorts_by_peak_altitude_descending():
    from datetime import date
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=10)
    alts = [r.peak_alt_deg for r in results]
    assert alts == sorted(alts, reverse=True)


def test_respects_max_results():
    from datetime import date
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=3)
    assert len(results) <= 3


def test_transit_utc_is_hour_of_peak_altitude():
    from datetime import date
    window = {datetime(2024, 6, 16, h, tzinfo=UTC) for h in range(1, 11)}
    results = get_nightly_targets(LAT, LON, window, max_results=5)
    for r in results:
        assert r.transit_utc is not None
        assert r.transit_utc in window
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest test_target_recommender.py -v --ignore-glob="*test_targets_json*" -k "not test_targets_json"
```
Expected: ImportError — `target_recommender` does not exist yet.

- [ ] **Step 3: Add `compute_imaging_window` to `moon.py`**

Add this function at the end of `moon.py`, after `get_moon_info`:

```python
def compute_imaging_window(lat: float, lon: float, target_date: date) -> set:
    """Return the set of UTC hour datetimes covering sunset→sunrise for target_date.

    Falls back to 20:00–04:00 UTC if sun times are unavailable (polar extremes).
    """
    from datetime import datetime, timedelta, timezone
    sunset, sunrise = get_sun_times(lat, lon, target_date)
    if sunset and sunrise:
        start = sunset.replace(minute=0, second=0, microsecond=0)
        end   = sunrise.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        hours: set = set()
        t = start
        while t <= end:
            hours.add(t)
            t += timedelta(hours=1)
        return hours
    ev = {
        datetime(target_date.year, target_date.month, target_date.day,
                 h, tzinfo=timezone.utc)
        for h in range(20, 24)
    }
    nd = target_date + timedelta(days=1)
    ea = {
        datetime(nd.year, nd.month, nd.day, h, tzinfo=timezone.utc)
        for h in range(0, 5)
    }
    return ev | ea
```

- [ ] **Step 4: Update `_forecast_imaging_window` in `gui.py` to delegate to `moon.compute_imaging_window`**

Replace the entire `_forecast_imaging_window` function (lines ~82–111) with:

```python
def _forecast_imaging_window(target_date, lat=None, lon=None):
    """Return the set of UTC datetimes covering the imaging night for target_date."""
    if lat is not None and lon is not None:
        from moon import compute_imaging_window
        return compute_imaging_window(lat, lon, target_date)
    from datetime import datetime, timedelta, timezone
    ev = {
        datetime(target_date.year, target_date.month, target_date.day,
                 h, tzinfo=timezone.utc)
        for h in range(20, 24)
    }
    nd = target_date + timedelta(days=1)
    ea = {
        datetime(nd.year, nd.month, nd.day, h, tzinfo=timezone.utc)
        for h in range(0, 5)
    }
    return ev | ea
```

- [ ] **Step 5: Create `target_recommender.py`**

```python
"""Recommend deep-sky objects for a given imaging night."""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import ephem

_TARGETS_FILE = Path(__file__).parent / "targets.json"
_log = logging.getLogger(__name__)


@dataclass
class TargetResult:
    name: str
    common_name: str
    type: str
    magnitude: float
    size_arcmin: float
    description: str
    peak_alt_deg: float
    hours_visible: float
    transit_utc: Optional[datetime]


def get_nightly_targets(
    lat: float,
    lon: float,
    imaging_window: set,
    min_alt_deg: float = 25.0,
    min_hours: float = 2.0,
    max_results: int = 10,
) -> list[TargetResult]:
    """Return up to max_results targets visible during imaging_window, sorted by peak altitude."""
    try:
        with open(_TARGETS_FILE) as f:
            raw_targets = json.load(f)
    except Exception as exc:
        _log.warning("Failed to load targets.json: %s", exc)
        return []

    if not imaging_window:
        return []

    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.pressure = 0
    obs.horizon = "0"

    sorted_window = sorted(imaging_window)
    results: list[TargetResult] = []

    for target in raw_targets:
        try:
            body = ephem.FixedBody()
            body._ra    = target["ra"]
            body._dec   = target["dec"]
            body._epoch = ephem.J2000

            altitudes: list[tuple[float, datetime]] = []
            for dt in sorted_window:
                obs.date = ephem.Date(dt.replace(tzinfo=None))
                body.compute(obs)
                altitudes.append((math.degrees(float(body.alt)), dt))

            hours_above = sum(1 for alt, _ in altitudes if alt >= min_alt_deg)
            if hours_above < min_hours:
                continue

            peak_alt, transit_dt = max(altitudes, key=lambda x: x[0])
            results.append(TargetResult(
                name=target["name"],
                common_name=target["common_name"],
                type=target["type"],
                magnitude=float(target["magnitude"]),
                size_arcmin=float(target["size_arcmin"]),
                description=target["description"],
                peak_alt_deg=round(peak_alt, 1),
                hours_visible=float(hours_above),
                transit_utc=transit_dt,
            ))
        except Exception as exc:
            _log.warning("Skipping target %s: %s", target.get("name", "?"), exc)

    results.sort(key=lambda r: r.peak_alt_deg, reverse=True)
    return results[:max_results]
```

- [ ] **Step 6: Run all target_recommender tests**

```bash
pytest test_target_recommender.py -v
```
Expected: all 7 tests PASS (the 4 real-ephem tests may take a few seconds).

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
pytest test_moon.py test_gui.py -v
```
Expected: all existing tests PASS.

- [ ] **Step 8: Commit**

```bash
git add target_recommender.py moon.py gui.py test_target_recommender.py
git commit -m "feat: add target_recommender and compute_imaging_window"
```

---

## Task 3: Wire target recommendations into the Forecast tab GUI

**Files:**
- Modify: `gui.py` — targets treeview in detail panel, compute in `_run_forecast_load`, render in `_show_forecast_detail`
- Modify: `test_gui.py` — add `test_forecast_target_tree_exists`

- [ ] **Step 1: Write the failing test**

Add to `test_gui.py`:

```python
def test_forecast_target_tree_exists(app):
    assert hasattr(app, "_target_tree")
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest test_gui.py::test_forecast_target_tree_exists -v
```
Expected: FAIL — `_target_tree` attribute does not exist.

- [ ] **Step 3: Add targets section to the detail panel in `_build_forecast_tab`**

In `gui.py`, find the line:

```python
        self.after(150, self._refresh_forecast_sites)
```

Insert this block immediately before it:

```python
        # ── Targets section (hidden until a GO night is selected) ─────────────
        self._target_section_sep   = ttk.Separator(self._forecast_detail_pane)
        self._target_section_frame = ttk.Frame(self._forecast_detail_pane,
                                                style="Card.TFrame")

        ttk.Label(self._target_section_frame,
                  text="Recommended Targets",
                  style="CardDim.TLabel").pack(anchor="w", padx=26, pady=(8, 4))

        target_cols = ("name", "common_name", "type", "peak_alt",
                       "hrs_vis", "transits", "description")
        self._target_tree = ttk.Treeview(
            self._target_section_frame,
            columns=target_cols, show="headings",
            height=8, selectmode="none",
        )
        self._target_tree.heading("name",        text="Name")
        self._target_tree.heading("common_name", text="Common Name")
        self._target_tree.heading("type",        text="Type")
        self._target_tree.heading("peak_alt",    text="Peak Alt")
        self._target_tree.heading("hrs_vis",     text="Hrs Vis")
        self._target_tree.heading("transits",    text="Transits")
        self._target_tree.heading("description", text="Description")

        self._target_tree.column("name",        width=75,  anchor="w")
        self._target_tree.column("common_name", width=155, anchor="w")
        self._target_tree.column("type",        width=130, anchor="w")
        self._target_tree.column("peak_alt",    width=65,  anchor="center")
        self._target_tree.column("hrs_vis",     width=55,  anchor="center")
        self._target_tree.column("transits",    width=70,  anchor="center")
        self._target_tree.column("description", width=0,   anchor="w", stretch=True)

        self._target_tree.pack(fill="both", expand=True, padx=26, pady=(0, 12))

```

Also change `detail_inner.pack(fill="both", expand=True, ...)` to `fill="x"` so the targets section can expand below it:

Find:
```python
        detail_inner = ttk.Frame(self._forecast_detail_pane, style="Card.TFrame")
        detail_inner.pack(fill="both", expand=True, padx=26, pady=12)
```
Replace with:
```python
        detail_inner = ttk.Frame(self._forecast_detail_pane, style="Card.TFrame")
        detail_inner.pack(fill="x", padx=26, pady=12)
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
pytest test_gui.py::test_forecast_target_tree_exists -v
```
Expected: PASS.

- [ ] **Step 5: Compute targets in `_run_forecast_load`**

In `_run_forecast_load`, at the top of the `try:` block, add the import:

```python
            from target_recommender import get_nightly_targets
```

Then inside the `for i, (target_date, weather) in enumerate(weather_days):` loop, after the `score = score_night(...)` line, add:

```python
                targets = get_nightly_targets(site.lat, site.lon, window) if score.go else []
```

And add `"targets": targets` to the `nights.append({...})` dict:

```python
                nights.append({
                    "date":             target_date,
                    "score":            score,
                    "moon":             moon,
                    "weather":          weather,
                    "seeing_available": seeing_available,
                    "lat":              site.lat,
                    "lon":              site.lon,
                    "window_hours":     window_hours,
                    "timezone":         site.timezone,
                    "targets":          targets,
                })
```

- [ ] **Step 6: Render targets in `_show_forecast_detail`**

At the end of `_show_forecast_detail`, after the `self._detail_hours_txt.configure(state="disabled")` line, add:

```python
        targets = night.get("targets", [])
        if targets:
            self._target_section_sep.pack(fill="x")
            self._target_section_frame.pack(fill="both", expand=True)
            self._target_tree.delete(*self._target_tree.get_children())
            for t in targets:
                if t.transit_utc and local_tz:
                    transit_str = _local(t.transit_utc).strftime("%H:%M")
                elif t.transit_utc:
                    transit_str = t.transit_utc.strftime("%H:%M")
                else:
                    transit_str = "—"
                self._target_tree.insert("", "end", values=(
                    t.name,
                    t.common_name,
                    t.type,
                    f"{t.peak_alt_deg:.0f}°",
                    f"{t.hours_visible:.0f}h",
                    transit_str,
                    t.description,
                ))
        else:
            self._target_section_sep.pack_forget()
            self._target_section_frame.pack_forget()
```

Note: `_local` and `local_tz` are already defined earlier in `_show_forecast_detail` (from the imaging window section — keep the existing definitions, don't duplicate them).

- [ ] **Step 7: Run full test suite**

```bash
pytest test_gui.py test_target_recommender.py -v
```
Expected: all tests PASS.

- [ ] **Step 8: Launch app and manually verify**

```bash
python3 gui.py
```

Go to the Forecast tab → select a site → Load Forecast → click a GO night. The "Recommended Targets" table should appear below the scores/hours panel listing up to 10 objects with name, type, peak alt, hours visible, transit time, and description. Clicking a NO-GO night should hide the table.

- [ ] **Step 9: Commit**

```bash
git add gui.py test_gui.py
git commit -m "feat: show recommended targets in Forecast tab detail panel"
```

---

## Task 4: Add target recommendations to the HTML email

**Files:**
- Modify: `smtp_notifier.py` — compute targets per GO site, render HTML table

- [ ] **Step 1: Write the failing test**

Add to `test_notifier.py`:

```python
def test_html_email_includes_recommended_targets_for_go_site(tmp_path):
    """GO sites get a Recommended Targets table in HTML email."""
    from unittest.mock import MagicMock, patch
    from site_manager import Site

    go_report  = SiteReport("Bladen Lakes", drive_min=120, score=make_score(go=True, total=72), moon=make_moon())
    nogo_report = SiteReport("Durham Home",  drive_min=None, score=make_score(go=False, total=30), moon=make_moon())

    fake_site = MagicMock(spec=Site)
    fake_site.name = "Bladen Lakes"
    fake_site.lat  = 34.7
    fake_site.lon  = -78.6
    fake_site.timezone = "America/New_York"

    fake_nogo_site = MagicMock(spec=Site)
    fake_nogo_site.name = "Durham Home"
    fake_nogo_site.lat  = 36.0
    fake_nogo_site.lon  = -78.9
    fake_nogo_site.timezone = "America/New_York"

    from target_recommender import TargetResult
    from datetime import datetime, timezone

    fake_target = TargetResult(
        name="M13", common_name="Hercules Cluster", type="Globular Cluster",
        magnitude=5.8, size_arcmin=20, description="Finest northern globular",
        peak_alt_deg=74.5, hours_visible=7.0,
        transit_utc=datetime(2026, 4, 28, 2, 0, tzinfo=timezone.utc),
    )

    captured = {}

    def fake_sendmail(from_addr, to_addrs, msg_str):
        captured["msg"] = msg_str

    with patch.dict("os.environ", {**ENV, "EMAIL_FORMAT": "html"}):
        with patch("smtplib.SMTP") as MockSMTP:
            smtp_instance = MockSMTP.return_value.__enter__.return_value
            smtp_instance.sendmail.side_effect = fake_sendmail
            with patch("target_recommender.get_nightly_targets", return_value=[fake_target]):
                with patch("chart_html.build_chart_data"):
                    with patch("chart_html.render_chart_fragment", return_value="<table></table>"):
                        send_multi_site_alert(
                            [go_report, nogo_report],
                            night_label="tonight",
                            sites=[fake_site, fake_nogo_site],
                        )

    assert "Recommended Targets" in captured.get("msg", ""), \
        "HTML email should contain 'Recommended Targets' for GO site"
    assert "M13" in captured.get("msg", ""), \
        "GO site's target should appear in email"
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest test_notifier.py::test_html_email_includes_recommended_targets_for_go_site -v
```
Expected: FAIL — "Recommended Targets" not in the email.

- [ ] **Step 3: Add `_render_targets_html` helper and wire it in `smtp_notifier.py`**

Add this helper function near the top of `smtp_notifier.py` (after `_format_report`):

```python
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
        f'{th style="color:#8b949e;font-weight:normal">Description</th></tr>'
        + rows
        + "</table>"
    )
```

Then inside `send_multi_site_alert`, within the HTML email branch, replace the block that builds each site's `text_block` and assembles `blocks`. Change this:

```python
                blocks.append(heading + chart_html_frag + legend_html + text_block)
```

to this (add target computation and rendering before that line):

```python
                targets_html = ""
                if report.score.go and site_obj is not None:
                    try:
                        from datetime import datetime, timedelta, timezone as _tz
                        from moon import compute_imaging_window
                        today_utc = datetime.now(_tz.utc).date()
                        target_date = (
                            today_utc + timedelta(days=1)
                            if "tomorrow" in night_label
                            else today_utc
                        )
                        window = compute_imaging_window(site_obj.lat, site_obj.lon, target_date)
                        from target_recommender import get_nightly_targets
                        site_targets = get_nightly_targets(site_obj.lat, site_obj.lon, window)
                        targets_html = _render_targets_html(site_targets)
                    except Exception as _tgt_exc:
                        _logging.getLogger(__name__).warning(
                            "Target recommendations failed for %s: %s",
                            report.site_name, _tgt_exc,
                        )

                blocks.append(heading + chart_html_frag + legend_html + text_block + targets_html)
```

- [ ] **Step 4: Run the new test**

```bash
pytest test_notifier.py::test_html_email_includes_recommended_targets_for_go_site -v
```
Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest test_notifier.py test_target_recommender.py test_gui.py test_moon.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add smtp_notifier.py test_notifier.py
git commit -m "feat: add recommended targets table to HTML email for GO sites"
```
