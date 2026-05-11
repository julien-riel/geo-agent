from pathlib import Path

import pytest

from geo_agent.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:e4b")
    monkeypatch.setenv("WFS_BASE_URL", "https://example.com/wfs")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_FEATURES_PER_QUERY", "1000")

    s = Settings()

    assert s.OLLAMA_MODEL == "gemma4:e4b"
    assert s.WFS_BASE_URL == "https://example.com/wfs"
    assert s.DATA_DIR == tmp_path
    assert s.MAX_FEATURES_PER_QUERY == 1000


def test_data_subdirectories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.results_dir == tmp_path / "results"
    assert s.sessions_dir == tmp_path / "sessions"
