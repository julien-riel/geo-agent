from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore
from geo_agent.services.spatial_ops import AttributePredicate


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.filter_attributes.get_services", lambda: services)
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
    r = await filter_attributes.coroutine(
        dataset_id=populated,
        predicate=AttributePredicate(property="longueur", op="gt", value=200),
        alias="longues",
        tool_call_id="t",
        state={"datasets": []},
    )
    new_meta_lite = r.update["datasets"][0]
    assert new_meta_lite["feature_count"] == 2
    new_meta = services.store.get_meta(new_meta_lite["id"])
    assert new_meta.lineage.parent_ids == [populated]
    assert new_meta.alias == "longues"
    assert new_meta.lineage.params == {"property": "longueur", "op": "gt", "value": 200}


async def test_filter_attributes_unknown_dataset_returns_command_with_error(services: Services) -> None:
    r = await filter_attributes.coroutine(
        dataset_id="result_999",
        predicate=AttributePredicate(property="x", op="eq", value=1),
        alias=None,
        tool_call_id="t",
        state={"datasets": []},
    )
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_filter_attributes_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError

    schema = filter_attributes.args_schema
    with pytest.raises(ValidationError) as exc_info:
        schema.model_validate({
            "dataset_id": "result_001",
            "predicate": {"property": "type", "op": "like", "value": "parc%"},  # 'like' not allowed here
            "tool_call_id": "t",
            "state": {},
        })
    errors = exc_info.value.errors()
    predicate_errors = [e for e in errors if e.get("loc", ()) and e["loc"][0] == "predicate"]
    assert predicate_errors, f"Expected a predicate validation error, got: {errors}"


async def test_filter_attributes_args_schema_accepts_in_operator() -> None:
    schema = filter_attributes.args_schema
    validated = schema.model_validate({
        "dataset_id": "result_001",
        "predicate": {"property": "type", "op": "in", "value": ["parc", "place"]},
        "tool_call_id": "t",
        "state": {},
    })
    assert validated.predicate.op == "in"
