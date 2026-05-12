from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.wfs.select_features import DatasetSource, PolygonSource, select_features
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
    monkeypatch.setattr("geo_agent.agent.tools.wfs.select_features.get_services", lambda: services)
    return services


async def test_select_features_with_polygon(services: Services) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=PolygonSource(type="polygon", polygon=polygon),
        spatial_predicate="within",
        alias="parcs_test",
        tool_call_id="t",
        state={"datasets": []},
    )

    new_meta_lite = result.update["datasets"][0]
    rid = new_meta_lite["id"]
    assert new_meta_lite["alias"] == "parcs_test"
    assert new_meta_lite["feature_count"] == 1
    assert new_meta_lite["parent_ids"] == []
    meta = services.store.get_meta(rid)
    assert meta.source.layer == "montreal:parcs"


async def test_select_features_chains_from_dataset_using_bbox(services: Services) -> None:
    rid = services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.6, 45.5]}, "properties": {}}]},
        {"source": {"type": "wfs", "layer": "montreal:parcs", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )

    result = await select_features.coroutine(
        layer="montreal:chaussees",
        geometry_source=DatasetSource(type="dataset", dataset_id=rid, use_geometry=False),
        spatial_predicate="intersects",
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )

    new_meta_lite = result.update["datasets"][0]
    new_id = new_meta_lite["id"]
    assert new_meta_lite["feature_count"] == 1
    new_meta = services.store.get_meta(new_id)
    assert new_meta.lineage.parent_ids == [rid]


async def test_select_features_too_many_returns_command_with_error(services: Services) -> None:
    from geo_agent.services.wfs_client import TooManyFeaturesError

    services.wfs.get_features.side_effect = TooManyFeaturesError(5000)

    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=PolygonSource(type="polygon", polygon=polygon),
        spatial_predicate="within",
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )

    assert result.update["errors"][0]["code"] == "too_many_features"


async def test_select_features_wfs_error_returns_command_not_exception(services: Services) -> None:
    from geo_agent.services.wfs_client import WFSRequestError

    services.wfs.get_features.side_effect = WFSRequestError(
        "WFS GetFeature on montreal:arrondissements failed (HTTP 400): [OperationParsingFailed] ..."
    )

    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.coroutine(
        layer="montreal:arrondissements",
        geometry_source=PolygonSource(type="polygon", polygon=polygon),
        spatial_predicate="intersects",
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )

    err = result.update["errors"][0]
    assert err["code"] == "wfs_error"
    assert "HTTP 400" in err["message"]


async def test_select_features_unknown_dataset_returns_command_with_suggestion(services: Services) -> None:
    result = await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=DatasetSource(type="dataset", dataset_id="result_999", use_geometry=False),
        spatial_predicate="intersects",
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )

    err = result.update["errors"][0]
    assert err["code"] == "dataset_not_found"
    assert "Available IDs" in err["suggestion"]


async def test_select_features_use_geometry_true_with_drawing(services: Services) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-73.6, 45.5], [-73.55, 45.5], [-73.55, 45.55], [-73.6, 45.55], [-73.6, 45.5]]],
    }
    drawing_id = services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": polygon, "properties": {}}]},
        {
            "source": {"type": "user_drawing", "filter_summary": "user-drawn polygon"},
            "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}},
        },
    )

    result = await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=DatasetSource(type="dataset", dataset_id=drawing_id, use_geometry=True),
        spatial_predicate="within",
        alias="parcs_in_zone",
        tool_call_id="t",
        state={"datasets": []},
    )

    assert result.update["datasets"][0]["alias"] == "parcs_in_zone"
    sf_arg = services.wfs.get_features.call_args.kwargs["spatial_filter"]
    assert sf_arg.geometry["type"] == "Polygon"
    assert sf_arg.geometry["coordinates"][0][0] == [-73.6, 45.5] or tuple(sf_arg.geometry["coordinates"][0][0]) == (-73.6, 45.5)


async def test_select_features_use_geometry_true_multipolygon_reaches_wfs(services: Services) -> None:
    parent_id = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}, "properties": {}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]}, "properties": {}},
            ],
        },
        {"source": {"type": "wfs", "layer": "montreal:parcs", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )

    result = await select_features.coroutine(
        layer="montreal:chaussees",
        geometry_source=DatasetSource(type="dataset", dataset_id=parent_id, use_geometry=True),
        spatial_predicate="intersects",
        alias="chaussees_multi",
        tool_call_id="t",
        state={"datasets": []},
    )

    assert "errors" not in result.update
    assert result.update["datasets"][0]["alias"] == "chaussees_multi"
    sf_arg = services.wfs.get_features.call_args.kwargs["spatial_filter"]
    assert sf_arg.geometry["type"] == "MultiPolygon"
    assert len(sf_arg.geometry["coordinates"]) == 2


async def test_select_features_use_geometry_true_nonpolygonal_returns_error(services: Services) -> None:
    parent_id = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "properties": {}},
            ],
        },
        {"source": {"type": "wfs", "layer": "montreal:rues", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )

    result = await select_features.coroutine(
        layer="montreal:chaussees",
        geometry_source=DatasetSource(type="dataset", dataset_id=parent_id, use_geometry=True),
        spatial_predicate="intersects",
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )

    assert result.update["errors"][0]["code"] == "unsupported_geometry"


async def test_select_features_args_schema_rejects_unknown_geometry_source_type(services: Services) -> None:
    from pydantic import ValidationError

    schema = select_features.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({
            "layer": "montreal:parcs",
            "geometry_source": {"type": "banana", "polygon": {}},
            "spatial_predicate": "within",
        })


async def test_select_features_with_attribute_filter_reaches_wfs(services: Services) -> None:
    from geo_agent.agent.tools.wfs.select_features import AttributeFilterInput, PolygonSource

    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=PolygonSource(type="polygon", polygon=polygon),
        spatial_predicate="within",
        attribute_filter=AttributeFilterInput(property="type", op="eq", value="parc"),
        alias="parcs_eq",
        tool_call_id="t",
        state={"datasets": []},
    )

    af_arg = services.wfs.get_features.call_args.kwargs["attribute_filter"]
    assert af_arg is not None
    assert af_arg.property == "type"
    assert af_arg.op == "eq"
    assert af_arg.value == "parc"


async def test_select_features_distance_meters_without_dwithin_is_bad_input(services: Services) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    result = await select_features.coroutine(
        layer="montreal:parcs",
        geometry_source=PolygonSource(type="polygon", polygon=polygon),
        spatial_predicate="within",
        distance_meters=50,
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )
    err = result.update["errors"][0]
    assert err["code"] == "bad_input"
    assert "dwithin" in err["message"]
    services.wfs.get_features.assert_not_called()


async def test_select_features_args_schema_accepts_dataset_source(services: Services) -> None:
    schema = select_features.args_schema
    validated = schema.model_validate({
        "layer": "montreal:parcs",
        "geometry_source": {"type": "dataset", "dataset_id": "result_001", "use_geometry": False},
        "spatial_predicate": "within",
        "tool_call_id": "t",
        "state": {},
    })
    assert validated.geometry_source.type == "dataset"
    assert validated.geometry_source.dataset_id == "result_001"
