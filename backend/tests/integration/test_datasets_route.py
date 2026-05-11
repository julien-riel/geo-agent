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


def test_post_drawing_creates_dataset(client) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-73.6, 45.5], [-73.55, 45.5], [-73.55, 45.55], [-73.6, 45.55], [-73.6, 45.5]]],
    }

    r = client.post("/datasets/drawing", json={"polygon": polygon})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"].startswith("result_")
    assert body["feature_count"] == 1
    assert body["operation"] == "user_drawing"
    assert body["alias"] == "zone_1"
    assert body["parent_ids"] == []
    minx, miny, maxx, maxy = body["bbox"]
    assert (minx, miny) == (-73.6, 45.5)
    assert (maxx, maxy) == (-73.55, 45.55)


def test_post_drawing_increments_zone_alias(client) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}

    a = client.post("/datasets/drawing", json={"polygon": polygon}).json()
    b = client.post("/datasets/drawing", json={"polygon": polygon}).json()

    assert a["alias"] == "zone_1"
    assert b["alias"] == "zone_2"


def test_post_drawing_rejects_non_polygon(client) -> None:
    r = client.post("/datasets/drawing", json={"polygon": {"type": "Point", "coordinates": [0, 0]}})
    assert r.status_code == 400
