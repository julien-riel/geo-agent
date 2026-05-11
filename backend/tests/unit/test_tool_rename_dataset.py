from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.rename_dataset import rename_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.rename_dataset.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_rename_dataset_updates_alias(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="park", state=state, tool_call_id="t"
    )

    assert isinstance(result, Command)
    assert services.store.get_meta(rid).alias == "park"
    assert result.update["datasets"][0]["alias"] == "park"


async def test_rename_dataset_rejects_whitespace(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="bad name", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"
    assert "datasets" not in result.update


async def test_rename_dataset_rejects_empty(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"


async def test_rename_dataset_rejects_too_long(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="x" * 65, state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"


async def test_rename_dataset_detects_alias_conflict(services: Services) -> None:
    rid_keep = _put(services, alias="park")
    rid_other = _put(services)
    state = {"datasets": [{"id": rid_keep, "alias": "park"}, {"id": rid_other, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid_other, new_alias="park", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "alias_conflict"
    assert services.store.get_meta(rid_other).alias is None


async def test_rename_dataset_same_alias_noop(services: Services) -> None:
    rid = _put(services, alias="park")
    state = {"datasets": [{"id": rid, "alias": "park"}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="park", state=state, tool_call_id="t"
    )

    # No error and the meta is unchanged.
    assert "errors" not in result.update
    assert services.store.get_meta(rid).alias == "park"


async def test_rename_dataset_missing_returns_dataset_not_found(services: Services) -> None:
    state = {"datasets": []}

    result = await rename_dataset.coroutine(
        id_or_alias="result_999", new_alias="park", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "dataset_not_found"
