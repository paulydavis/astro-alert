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
