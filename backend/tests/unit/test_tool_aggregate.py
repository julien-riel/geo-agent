from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.aggregate import aggregate as aggregate_tool
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.aggregate.get_services", lambda: services)
    return services


@pytest.fixture
def populated_dataset(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"type": "rue", "longueur": 100}},
                {"type": "Feature", "geometry": None, "properties": {"type": "rue", "longueur": 200}},
                {"type": "Feature", "geometry": None, "properties": {"type": "boulevard", "longueur": 1000}},
            ],
        },
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_aggregate_count(services: Services, populated_dataset: str) -> None:
    r = await aggregate_tool.coroutine(dataset_id=populated_dataset, op="count", tool_call_id="t")
    assert r["value"] == 3


async def test_aggregate_sum_with_attribute(services: Services, populated_dataset: str) -> None:
    r = await aggregate_tool.coroutine(dataset_id=populated_dataset, op="sum", attribute="longueur", tool_call_id="t")
    assert r["value"] == 1300


async def test_aggregate_with_group_by(services: Services, populated_dataset: str) -> None:
    r = await aggregate_tool.coroutine(
        dataset_id=populated_dataset, op="sum", attribute="longueur", group_by="type", tool_call_id="t"
    )
    groups = {g["key"]: g["value"] for g in r["groups"]}
    assert groups == {"rue": 300, "boulevard": 1000}


async def test_aggregate_unknown_dataset_returns_command_with_error(services: Services) -> None:
    r = await aggregate_tool.coroutine(dataset_id="result_999", op="count", tool_call_id="t")
    # Error path returns a Command with errors appended to state and a ToolMessage
    assert r.update["errors"][0]["code"] == "dataset_not_found"
    assert r.update["errors"][0]["suggestion"] == "Available IDs: (none)"
    assert r.update["messages"][0].tool_call_id == "t"
