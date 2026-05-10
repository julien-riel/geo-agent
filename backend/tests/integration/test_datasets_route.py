from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "results").mkdir()
    (tmp_path / "sessions").mkdir()
    # Force reimport of main with new env
    import importlib

    import geo_agent.main as main_mod
    importlib.reload(main_mod)
    with TestClient(main_mod.app) as c:
        yield c


def _put_dataset(tmp_path: Path) -> str:
    from geo_agent.config import Settings
    from geo_agent.services.result_store import FileSystemResultStore

    s = Settings()
    store = FileSystemResultStore(data_dir=s.DATA_DIR)
    return store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


def test_get_dataset_geojson(client: TestClient, tmp_path: Path) -> None:
    rid = _put_dataset(tmp_path)
    r = client.get(f"/datasets/{rid}/geojson")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"


def test_get_dataset_meta(client: TestClient, tmp_path: Path) -> None:
    rid = _put_dataset(tmp_path)
    r = client.get(f"/datasets/{rid}/meta")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == rid


def test_list_datasets(client: TestClient, tmp_path: Path) -> None:
    _put_dataset(tmp_path)
    _put_dataset(tmp_path)
    r = client.get("/datasets")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_dataset_not_found(client: TestClient) -> None:
    r = client.get("/datasets/result_999/geojson")
    assert r.status_code == 404
