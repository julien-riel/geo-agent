from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.filter_attributes import filter_attributes
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.filter_attributes.get_services", lambda: services)
    return services


@pytest.fixture
def populated(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"longueur": 100}},
                {"type": "Feature", "geometry": None, "properties": {"longueur": 250}},
                {"type": "Feature", "geometry": None, "properties": {"longueur": 500}},
            ],
        },
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_filter_attributes_creates_new_dataset(services: Services, populated: str) -> None:
    r = await filter_attributes.ainvoke({
        "dataset_id": populated,
        "predicate": {"property": "longueur", "op": "gt", "value": 200},
        "alias": "longues",
    })
    assert r["feature_count"] == 2
    new_meta = services.store.get_meta(r["dataset_id"])
    assert new_meta.lineage.parent_ids == [populated]
    assert new_meta.alias == "longues"
