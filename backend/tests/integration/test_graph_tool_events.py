"""Integration: invoking a tool through its instrumented wrapper writes a final
tool_events entry into the returned Command. Uses select_features as a witness
for the whole decorator pipeline (which is uniform across all 15 tools)."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.wfs.select_features import PolygonSource, select_features
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore
from geo_agent.services.wfs_client import FeatureTypeSchema


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    wfs = AsyncMock()
    wfs.describe_feature_type.return_value = FeatureTypeSchema(
        type_name="montreal:parcs",
        geom_property="geom",
        attribute_schema={"nom": "string"},
    )
    wfs.get_features.return_value = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"nom": "parc A"},
            }
        ],
    }
    services = Services(settings=settings, wfs=wfs, store=FileSystemResultStore(data_dir=data_dir))
    monkeypatch.setattr("geo_agent.agent.tools.wfs.select_features.get_services", lambda: services)
    return services


async def test_select_features_emits_final_tool_event(services: Services) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    call = {
        "name": "select_features",
        "args": {
            "layer": "montreal:parcs",
            "geometry_source": PolygonSource(type="polygon", polygon=polygon).model_dump(),
            "spatial_predicate": "within",
            "alias": "parcs_test",
            "state": {"datasets": []},
        },
        "id": "tc_abc",
        "type": "tool_call",
    }
    cmd = await select_features.ainvoke(call)
    events = cmd.update["tool_events"]
    assert len(events) == 1
    ev = events[0]
    assert ev["status"] == "ok"
    assert ev["tool"] == "select_features"
    assert ev["tool_call_id"] == "tc_abc"
    assert ev["duration_ms"] is not None and ev["duration_ms"] >= 0
    assert ev["args_summary"].startswith("layer=montreal:parcs")
    assert "1 features → " in ev["result_summary"]
