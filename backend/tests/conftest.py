from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "results").mkdir()
    (tmp_path / "sessions").mkdir()
    return tmp_path
