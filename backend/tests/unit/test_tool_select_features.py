from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.select_features import select_features
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore
from geo_agent.services.wfs_client import FeatureTypeSchema


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    wfs_mock = AsyncMock()
    wfs_mock.describe_feature_type.return_value = FeatureTypeSchema(
        type_name="montreal:parcs",
        geom_property="geom",
        attribute_schema={"nom": "string"},
    )
    wfs_mock.get_features.return_value = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {"nom": "parc A"}}
        ],
    }
    services = Services(settings=settings, wfs=wfs_mock, store=FileSystemResultStore(data_dir=data_dir))
    monkeypatch.setattr("geo_agent.agent.tools.select_features.get_services", lambda: services)
    return services


async def test_select_features_with_polygon(services: Services) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.ainvoke(
        {
            "layer": "montreal:parcs",
            "geometry_source": {"type": "polygon", "polygon": polygon},
            "spatial_predicate": "within",
            "alias": "parcs_test",
        }
    )

    assert "dataset_id" in result
    assert result["feature_count"] == 1
    meta = services.store.get_meta(result["dataset_id"])
    assert meta.alias == "parcs_test"
    assert meta.source.layer == "montreal:parcs"


async def test_select_features_chains_from_dataset_using_bbox(services: Services) -> None:
    # Pre-populate a dataset with a known bbox
    rid = services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.6, 45.5]}, "properties": {}}]},
        {"source": {"type": "wfs", "layer": "montreal:parcs", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )

    result = await select_features.ainvoke(
        {
            "layer": "montreal:chaussees",
            "geometry_source": {"type": "dataset", "dataset_id": rid, "use_geometry": False},
            "spatial_predicate": "intersects",
            "alias": None,
        }
    )

    assert result["feature_count"] == 1
    new_meta = services.store.get_meta(result["dataset_id"])
    assert new_meta.lineage.parent_ids == [rid]


async def test_select_features_too_many_returns_error(services: Services) -> None:
    from geo_agent.services.wfs_client import TooManyFeaturesError

    services.wfs.get_features.side_effect = TooManyFeaturesError(5000)

    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.ainvoke(
        {
            "layer": "montreal:parcs",
            "geometry_source": {"type": "polygon", "polygon": polygon},
            "spatial_predicate": "within",
            "alias": None,
        }
    )

    assert result["error"]["code"] == "too_many_features"
