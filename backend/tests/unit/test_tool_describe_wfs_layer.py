from unittest.mock import AsyncMock

import httpx
import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer
from geo_agent.config import Settings
from geo_agent.services.wfs_client import FeatureTypeSchema


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> Services:
    wfs_mock = AsyncMock()
    wfs_mock.describe_feature_type.return_value = FeatureTypeSchema(
        type_name="montreal:chaussees",
        geom_property="geom",
        attribute_schema={"nom_voie": "string", "longueur": "number"},
    )
    services = Services(settings=Settings(), wfs=wfs_mock, store=None)  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.wfs.describe_layer.get_services", lambda: services)
    return services


async def test_describe_wfs_layer_returns_attributes(services: Services) -> None:
    out = await describe_wfs_layer.coroutine(layer="montreal:chaussees", tool_call_id="t")
    assert out == {
        "layer": "montreal:chaussees",
        "geometry_property": "geom",
        "attributes": {"nom_voie": "string", "longueur": "number"},
    }


async def test_describe_wfs_layer_http_error_returns_layer_not_found(services: Services) -> None:
    services.wfs.describe_feature_type.side_effect = httpx.HTTPStatusError(
        "404", request=httpx.Request("GET", "http://wfs"), response=httpx.Response(404)
    )
    out = await describe_wfs_layer.coroutine(layer="montreal:bogus", tool_call_id="t")
    assert out.update["errors"][0]["code"] == "layer_not_found"
