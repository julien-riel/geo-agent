from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.spatial_join import spatial_join
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.spatial_join.get_services", lambda: services)
    return services


def _put(services: Services, geojson: dict, alias: str | None = None) -> str:
    return services.store.put(
        geojson,
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_spatial_join_creates_dataset_with_two_parents(services: Services) -> None:
    pts = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {"id": "p1"}}]}, alias="points")
    zones = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]]}, "properties": {"zone": "A"}}]}, alias="zones")

    r = await spatial_join.coroutine(left_id=pts, right_id=zones, predicate="within", alias="points_zoned", tool_call_id="t", state={"datasets": []})

    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "points_zoned"
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [pts, zones]
    assert meta.lineage.operation == "spatial_join"
    assert meta.lineage.params == {"predicate": "within"}
    # the joined attribute is present in the stored geojson
    gj = services.store.get_geojson(meta_lite["id"])
    assert gj["features"][0]["properties"]["zone_r"] == "A"


async def test_spatial_join_unknown_right_returns_error(services: Services) -> None:
    pts = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {}}]})
    r = await spatial_join.coroutine(left_id=pts, right_id="result_999", predicate="within", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_spatial_join_args_schema_rejects_unknown_predicate() -> None:
    from pydantic import ValidationError

    schema = spatial_join.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"left_id": "result_001", "right_id": "result_002", "predicate": "banana", "tool_call_id": "t", "state": {}})
