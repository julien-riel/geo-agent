from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.ui.show_on_map.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_show_on_map_appends_to_active_layers(services: Services) -> None:
    rid = _put(services)
    state = {"active_layers": ["other_001"]}
    result = await show_on_map.coroutine(dataset_id=rid, state=state, tool_call_id="t")
    assert isinstance(result, Command)
    assert result.update["active_layers"] == ["other_001", rid]


async def test_show_on_map_no_duplicate_when_already_visible(services: Services) -> None:
    rid = _put(services)
    state = {"active_layers": [rid]}
    result = await show_on_map.coroutine(dataset_id=rid, state=state, tool_call_id="t")
    assert result.update["active_layers"] == [rid]


async def test_show_on_map_unknown_dataset_returns_error(services: Services) -> None:
    state = {"active_layers": []}
    result = await show_on_map.coroutine(dataset_id="result_999", state=state, tool_call_id="t")
    assert result.update["errors"][0]["code"] == "dataset_not_found"
    assert "active_layers" not in result.update


async def test_hide_on_map_removes_from_active_layers(services: Services) -> None:
    rid = _put(services)
    state = {"active_layers": [rid, "result_002"]}
    result = await hide_on_map.coroutine(dataset_id=rid, state=state, tool_call_id="t")
    assert isinstance(result, Command)
    assert result.update["active_layers"] == ["result_002"]


async def test_hide_on_map_idempotent_when_not_visible(services: Services) -> None:
    state = {"active_layers": ["result_002"]}
    result = await hide_on_map.coroutine(dataset_id="result_001", state=state, tool_call_id="t")
    assert result.update["active_layers"] == ["result_002"]
