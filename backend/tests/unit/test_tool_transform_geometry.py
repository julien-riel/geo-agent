from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.transform_geometry.get_services", lambda: services)
    return services


def _put_poly(services: Services) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-73.6, 45.5], [-73.5, 45.5], [-73.5, 45.6], [-73.6, 45.6], [-73.6, 45.5]]]}, "properties": {"k": 1}}]},
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_transform_geometry_centroid_creates_dataset(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="centroid", alias="centres", tool_call_id="t", state={"datasets": []})
    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "centres"
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [rid]
    assert meta.lineage.operation == "transform_geometry"
    assert meta.lineage.params == {"op": "centroid"}


async def test_transform_geometry_buffer_records_distance_in_lineage(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="buffer", distance_meters=50, alias=None, tool_call_id="t", state={"datasets": []})
    meta = services.store.get_meta(r.update["datasets"][0]["id"])
    assert meta.lineage.params == {"op": "buffer", "distance_meters": 50}


async def test_transform_geometry_buffer_without_distance_is_bad_input(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="buffer", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "bad_input"


async def test_transform_geometry_unknown_dataset_returns_error(services: Services) -> None:
    r = await transform_geometry.coroutine(dataset_id="result_999", op="centroid", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_transform_geometry_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError

    schema = transform_geometry.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"dataset_id": "result_001", "op": "banana", "tool_call_id": "t", "state": {}})
