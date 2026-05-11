import json
from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.ui.inspect_dataset import inspect_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.ui.inspect_dataset.get_services", lambda: services)
    return services


@pytest.fixture
def rid(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.6, 45.5]}, "properties": {"nom": "A", "n": 1}},
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 2]]}, "properties": {"nom": "B", "n": 2}},
            ],
        },
        {"alias": "ds", "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


def _inspection_payload(cmd) -> dict:
    return cmd.update["inspections"][0]


def _model_summary(cmd) -> dict:
    return json.loads(cmd.update["messages"][0].content)


async def test_inspect_schema_pushes_payload_to_state_and_compact_summary_to_model(services: Services, rid: str) -> None:
    cmd = await inspect_dataset.coroutine(dataset_id=rid, view="schema", tool_call_id="t")
    payload = _inspection_payload(cmd)
    assert payload["view"] == "schema"
    assert payload["dataset_id"] == rid
    assert payload["attribute_schema"] == {"nom": "string", "n": "number"}
    assert payload["sample"] == {"nom": "A", "n": 1}

    summary = _model_summary(cmd)
    assert summary == {"shown_to_user": "schema", "dataset_id": rid, "alias": "ds", "feature_count": 2}
    # the model must NOT receive the schema/sample table itself
    assert "attribute_schema" not in summary


async def test_inspect_features_payload_has_rows_without_coordinates_summary_has_counts(services: Services, rid: str) -> None:
    cmd = await inspect_dataset.coroutine(dataset_id=rid, view="features", tool_call_id="t")
    payload = _inspection_payload(cmd)
    assert payload["view"] == "features"
    assert payload["total"] == 2
    assert [f["index"] for f in payload["features"]] == [0, 1]
    assert payload["features"][0]["geometry_type"] == "Point"
    assert payload["features"][1]["geometry_type"] == "LineString"
    assert "coordinates" not in json.dumps(payload)

    summary = _model_summary(cmd)
    assert summary["shown_to_user"] == "features"
    assert summary["feature_count"] == 2
    assert summary["rows_shown"] == 2
    assert "features" not in summary


async def test_inspect_feature_payload_has_properties_and_vertex_count(services: Services, rid: str) -> None:
    cmd = await inspect_dataset.coroutine(dataset_id=rid, view="feature", feature_index=1, tool_call_id="t")
    payload = _inspection_payload(cmd)
    assert payload["view"] == "feature"
    assert payload["index"] == 1
    assert payload["properties"] == {"nom": "B", "n": 2}
    assert payload["geometry_type"] == "LineString"
    assert payload["vertex_count"] == 3

    summary = _model_summary(cmd)
    assert summary == {"shown_to_user": "feature", "dataset_id": rid, "alias": "ds", "feature_index": 1, "geometry_type": "LineString"}


async def test_inspect_feature_out_of_range_is_bad_input(services: Services, rid: str) -> None:
    out = await inspect_dataset.coroutine(dataset_id=rid, view="feature", feature_index=99, tool_call_id="t")
    assert out.update["errors"][0]["code"] == "bad_input"


async def test_inspect_unknown_dataset_returns_error(services: Services) -> None:
    out = await inspect_dataset.coroutine(dataset_id="result_999", view="schema", tool_call_id="t")
    assert out.update["errors"][0]["code"] == "dataset_not_found"


async def test_inspect_args_schema_rejects_unknown_view() -> None:
    from pydantic import ValidationError

    schema = inspect_dataset.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"dataset_id": "result_001", "view": "banana", "tool_call_id": "t"})
