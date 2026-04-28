import json
from pathlib import Path


def test_targets_json_loads_and_has_required_fields():
    data = json.loads((Path(__file__).parent / "targets.json").read_text())
    assert len(data) >= 90
    required = {"name", "common_name", "type", "ra", "dec", "magnitude", "size_arcmin", "description"}
    for entry in data:
        missing = required - entry.keys()
        assert not missing, f"{entry.get('name', '?')} missing: {missing}"
