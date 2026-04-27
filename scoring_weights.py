"""Global scoring weights for the go/no-go scorer."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path

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
