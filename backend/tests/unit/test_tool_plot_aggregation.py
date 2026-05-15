from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.ui.plot_aggregation import plot_aggregation
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(
        settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir)  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        "geo_agent.agent.tools.ui.plot_aggregation.get_services", lambda: services
    )
    return services


@pytest.fixture
def populated_dataset(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"t": "a", "v": 10}},
                {"type": "Feature", "geometry": None, "properties": {"t": "a", "v": 20}},
                {"type": "Feature", "geometry": None, "properties": {"t": "b", "v": 5}},
            ],
        },
        {
            "alias": "voies",
            "source": {"type": "wfs", "layer": "x", "filter_summary": ""},
            "lineage": {"parent_ids": [], "operation": "select", "params": {}},
        },
    )


async def test_count_grouped_returns_grouped_bar(services: Services, populated_dataset: str) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id=populated_dataset, group_by="t", op="count", tool_call_id="t"
    )
    assert r["chart_type"] == "grouped_bar"
    values = {p["label"]: p["value"] for p in r["series"]}
    assert values == {"a": 2.0, "b": 1.0}


async def test_sum_requires_metric(services: Services, populated_dataset: str) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id=populated_dataset, group_by="t", op="sum", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "bad_input"
    assert "metric" in r.update["errors"][0]["message"].lower()


async def test_sum_with_metric(services: Services, populated_dataset: str) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id=populated_dataset, group_by="t", op="sum", metric="v", tool_call_id="t"
    )
    values = {p["label"]: p["value"] for p in r["series"]}
    assert values == {"a": 30.0, "b": 5.0}


async def test_unknown_dataset(services: Services) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id="result_999", group_by="t", op="count", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_unknown_group_by(services: Services, populated_dataset: str) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id=populated_dataset, group_by="nope", op="count", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "bad_input"
    assert "nope" in r.update["errors"][0]["message"]


async def test_unknown_metric(services: Services, populated_dataset: str) -> None:
    r = await plot_aggregation.coroutine(
        dataset_id=populated_dataset, group_by="t", op="sum", metric="nope", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "bad_input"
    assert "nope" in r.update["errors"][0]["message"]
    assert "metric" in r.update["errors"][0]["message"]
