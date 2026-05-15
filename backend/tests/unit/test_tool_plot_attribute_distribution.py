from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.ui.plot_attribute_distribution import plot_attribute_distribution
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(
        settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir)  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        "geo_agent.agent.tools.ui.plot_attribute_distribution.get_services",
        lambda: services,
    )
    return services


@pytest.fixture
def populated_dataset(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"type": "rue"}},
                {"type": "Feature", "geometry": None, "properties": {"type": "rue"}},
                {"type": "Feature", "geometry": None, "properties": {"type": "boulevard"}},
            ],
        },
        {
            "alias": "voies",
            "source": {"type": "wfs", "layer": "x", "filter_summary": ""},
            "lineage": {"parent_ids": [], "operation": "select", "params": {}},
        },
    )


async def test_returns_chart_data_shape(services: Services, populated_dataset: str) -> None:
    r = await plot_attribute_distribution.coroutine(
        dataset_id=populated_dataset, attribute="type", chart_type="bar", tool_call_id="t"
    )
    assert r["chart_type"] == "bar"
    assert r["source"] == "attribute_distribution"
    assert r["attribute"] == "type"
    assert r["dataset_id"] == populated_dataset
    assert r["dataset_alias"] == "voies"
    assert r["total_features"] == 3
    labels = [p["label"] for p in r["series"]]
    assert labels == ["rue", "boulevard"]


async def test_dataset_not_found_returns_error_command(services: Services) -> None:
    r = await plot_attribute_distribution.coroutine(
        dataset_id="result_999", attribute="x", chart_type="bar", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_unknown_attribute_returns_bad_input(services: Services, populated_dataset: str) -> None:
    r = await plot_attribute_distribution.coroutine(
        dataset_id=populated_dataset, attribute="nope", chart_type="bar", tool_call_id="t"
    )
    assert r.update["errors"][0]["code"] == "bad_input"
    assert "nope" in r.update["errors"][0]["message"]
