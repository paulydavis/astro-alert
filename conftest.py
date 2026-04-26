"""Session-wide test fixtures for astro_alert."""

import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_env_file(tmp_path, monkeypatch):
    """Point data_dir.ENV_FILE at a temp file so tests never touch the real .env."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr("data_dir.ENV_FILE", fake_env)
    # Also patch it in modules that imported it at load time
    import smtp_notifier
    import scheduler_setup
    monkeypatch.setattr(smtp_notifier, "__file__", smtp_notifier.__file__)
    return fake_env
