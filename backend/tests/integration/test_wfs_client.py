from pathlib import Path

import httpx
import pytest
import respx

from geo_agent.services.wfs_client import WFSClient


@pytest.fixture
def capabilities_xml() -> bytes:
    return (Path(__file__).parent.parent / "fixtures" / "wfs_capabilities_2.0.0.xml").read_bytes()


@respx.mock
async def test_get_layers_fetches_and_caches(tmp_path: Path, capabilities_xml: bytes) -> None:
    base = "https://example.test/wfs"
    route = respx.get(base).mock(return_value=httpx.Response(200, content=capabilities_xml))

    client = WFSClient(base_url=base, cache_dir=tmp_path, http_timeout_seconds=10)

    layers1 = await client.get_layers()
    layers2 = await client.get_layers()

    assert len(layers1) >= 2
    assert layers1 == layers2
    assert route.call_count == 1  # second call hit the cache


async def test_get_layers_loads_from_disk_cache(tmp_path: Path, capabilities_xml: bytes) -> None:
    (tmp_path / "wfs_capabilities_cache.xml").write_bytes(capabilities_xml)

    client = WFSClient(base_url="https://example.test/wfs", cache_dir=tmp_path, http_timeout_seconds=10)
    # No respx.mock — if it tried to call HTTP, it would fail
    layers = await client.get_layers()
    assert len(layers) >= 2


@respx.mock
async def test_describe_feature_type(tmp_path: Path, capabilities_xml: bytes) -> None:
    schema_xml = (Path(__file__).parent.parent / "fixtures" / "describe_feature_type_chaussees.xml").read_bytes()
    base = "https://example.test/wfs"
    respx.get(base, params={"service": "WFS", "version": "2.0.0", "request": "DescribeFeatureType", "typeName": "montreal:chaussees"}).mock(
        return_value=httpx.Response(200, content=schema_xml)
    )
    respx.get(base).mock(return_value=httpx.Response(200, content=capabilities_xml))

    client = WFSClient(base_url=base, cache_dir=tmp_path)
    schema = await client.describe_feature_type("montreal:chaussees")

    assert schema.geom_property == "geom"
    assert schema.attribute_schema["longueur_m"] == "number"
    assert schema.attribute_schema["nom"] == "string"
