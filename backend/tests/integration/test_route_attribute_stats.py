from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "results").mkdir()
    (tmp_path / "sessions").mkdir()
    import importlib
    import geo_agent.main as main_mod
    importlib.reload(main_mod)
    with TestClient(main_mod.app) as c:
        yield c


def _put_dataset_with_props(props_list: list[dict]) -> str:
    from geo_agent.config import Settings
    from geo_agent.services.result_store import FileSystemResultStore

    s = Settings()
    store = FileSystemResultStore(data_dir=s.DATA_DIR)
    return store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": p}
                for p in props_list
            ],
        },
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


def test_attribute_stats_returns_payload(client: TestClient) -> None:
    rid = _put_dataset_with_props([{"len": 1.0}, {"len": 2.0}, {"len": 3.0}])
    r = client.get(f"/datasets/{rid}/attributes/len/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["attribute"] == "len"
    assert data["type"] == "number"
    assert data["min"] == 1.0
    assert data["max"] == 3.0


def test_attribute_stats_404_when_dataset_missing(client: TestClient) -> None:
    r = client.get("/datasets/result_999/attributes/foo/stats")
    assert r.status_code == 404


def test_attribute_stats_404_when_attribute_missing(client: TestClient) -> None:
    rid = _put_dataset_with_props([{"a": 1}])
    r = client.get(f"/datasets/{rid}/attributes/nope/stats")
    assert r.status_code == 404
