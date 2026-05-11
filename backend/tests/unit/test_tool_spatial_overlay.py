from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.spatial_overlay.get_services", lambda: services)
    return services


def _put_poly(services: Services, coords: list, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": {"k": 1}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_spatial_overlay_intersection_creates_dataset_with_two_parents(services: Services) -> None:
    left = _put_poly(services, [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], alias="a")
    right = _put_poly(services, [[5, 5], [15, 5], [15, 15], [5, 15], [5, 5]], alias="b")

    r = await spatial_overlay.coroutine(left_id=left, right_id=right, op="intersection", alias="overlap", tool_call_id="t", state={"datasets": []})

    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "overlap"
    assert meta_lite["feature_count"] == 1
    assert meta_lite["parent_ids"] == [left, right]
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [left, right]
    assert meta.lineage.operation == "spatial_overlay"
    assert meta.lineage.params == {"op": "intersection"}


async def test_spatial_overlay_unknown_left_returns_error(services: Services) -> None:
    right = _put_poly(services, [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    r = await spatial_overlay.coroutine(left_id="result_999", right_id=right, op="intersection", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_spatial_overlay_empty_result_when_disjoint(services: Services) -> None:
    left = _put_poly(services, [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    right = _put_poly(services, [[100, 100], [101, 100], [101, 101], [100, 101], [100, 100]])
    r = await spatial_overlay.coroutine(left_id=left, right_id=right, op="intersection", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "empty_result"


async def test_spatial_overlay_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError

    schema = spatial_overlay.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"left_id": "result_001", "right_id": "result_002", "op": "banana", "tool_call_id": "t", "state": {}})
