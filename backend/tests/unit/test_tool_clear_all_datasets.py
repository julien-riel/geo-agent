from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.clear_all_datasets import clear_all_datasets
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.clear_all_datasets.get_services", lambda: services)
    return services


def _put(services: Services) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_clear_all_datasets_removes_everything(services: Services) -> None:
    _put(services)
    _put(services)
    _put(services)
    state = {"datasets": [{"id": "result_001"}, {"id": "result_002"}, {"id": "result_003"}], "active_layers": ["result_001", "result_002"]}

    result = await clear_all_datasets.coroutine(state=state, tool_call_id="t")

    assert isinstance(result, Command)
    assert result.update["datasets"] == []
    assert result.update["active_layers"] == []
    assert services.store.list() == []


async def test_clear_all_datasets_is_idempotent_on_empty_store(services: Services) -> None:
    state = {"datasets": [], "active_layers": []}

    result = await clear_all_datasets.coroutine(state=state, tool_call_id="t")

    assert result.update["datasets"] == []
    assert result.update["active_layers"] == []
    assert "errors" not in result.update
