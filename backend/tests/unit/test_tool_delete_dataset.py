from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.delete_dataset import delete_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.delete_dataset.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_delete_dataset_removes_files_and_state(services: Services) -> None:
    rid_keep = _put(services)
    rid_drop = _put(services)
    state = {"datasets": [{"id": rid_keep}, {"id": rid_drop}], "active_layers": [rid_drop, rid_keep]}

    result = await delete_dataset.coroutine(id_or_alias=rid_drop, state=state, tool_call_id="t")

    assert isinstance(result, Command)
    assert [d["id"] for d in result.update["datasets"]] == [rid_keep]
    assert result.update["active_layers"] == [rid_keep]
    # Store side-effect: the dropped dataset is gone, the kept one survives.
    with pytest.raises(FileNotFoundError):
        services.store.get_meta(rid_drop)
    assert services.store.get_meta(rid_keep).id == rid_keep


async def test_delete_dataset_accepts_alias(services: Services) -> None:
    rid = _put(services, alias="park")
    state = {"datasets": [{"id": rid}], "active_layers": []}

    result = await delete_dataset.coroutine(id_or_alias="park", state=state, tool_call_id="t")

    assert result.update["datasets"] == []
    with pytest.raises(FileNotFoundError):
        services.store.get_meta(rid)


async def test_delete_dataset_missing_returns_dataset_not_found(services: Services) -> None:
    state = {"datasets": [], "active_layers": []}

    result = await delete_dataset.coroutine(id_or_alias="result_999", state=state, tool_call_id="t")

    assert result.update["errors"][0]["code"] == "dataset_not_found"
    assert "datasets" not in result.update
    assert "active_layers" not in result.update
