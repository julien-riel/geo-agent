from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.describe_dataset import describe_dataset
from geo_agent.agent.tools.list_datasets import list_datasets
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    for mod in ("describe_dataset", "list_datasets"):
        monkeypatch.setattr(f"geo_agent.agent.tools.{mod}.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_describe_dataset_by_id(services: Services) -> None:
    rid = _put(services, alias="my_data")
    r = await describe_dataset.coroutine(id_or_alias=rid, tool_call_id="t")
    assert r["id"] == rid
    assert r["alias"] == "my_data"


async def test_describe_dataset_by_alias(services: Services) -> None:
    _put(services, alias="parcs")
    r = await describe_dataset.coroutine(id_or_alias="parcs", tool_call_id="t")
    assert r["alias"] == "parcs"


async def test_describe_dataset_unknown_returns_command_with_error(services: Services) -> None:
    _put(services, alias="parcs")
    r = await describe_dataset.coroutine(id_or_alias="nope", tool_call_id="t")
    err = r.update["errors"][0]
    assert err["code"] == "dataset_not_found"
    assert "parcs" in err["suggestion"]


async def test_list_datasets_empty(services: Services) -> None:
    r = await list_datasets.ainvoke({})
    assert r == []


async def test_list_datasets_returns_lite_metadata(services: Services) -> None:
    _put(services, alias="a")
    _put(services, alias="b")
    r = await list_datasets.ainvoke({})
    assert len(r) == 2
    assert {x["alias"] for x in r} == {"a", "b"}
    assert "feature_count" in r[0]
    assert "bbox" in r[0]
