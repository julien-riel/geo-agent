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


from geo_agent.services.ogc_filter import SpatialFilter


@respx.mock
async def test_get_features_with_filter(tmp_path: Path) -> None:
    base = "https://example.test/wfs"
    sample_geojson = b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[-73.6,45.5]},"properties":{"nom":"X"}}]}'

    route = respx.post(base).mock(return_value=httpx.Response(200, content=sample_geojson))

    client = WFSClient(base_url=base, cache_dir=tmp_path)
    sf = SpatialFilter(
        predicate="intersects",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        geom_property="geom",
    )

    result = await client.get_features(
        layer="montreal:chaussees",
        spatial_filter=sf,
        attribute_filter=None,
        max_features=100,
    )

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1

    # Verify the request body was a WFS GetFeature with our filter
    sent = route.calls[0].request
    body = sent.content.decode("utf-8")
    assert "GetFeature" in body
    assert "Intersects" in body
    assert "montreal:chaussees" in body


@respx.mock
async def test_get_features_too_many_raises(tmp_path: Path) -> None:
    from geo_agent.services.wfs_client import TooManyFeaturesError

    base = "https://example.test/wfs"
    # Return 6 features when cap is 5 (max+1)
    feats = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}
        for _ in range(6)
    ]
    payload = {"type": "FeatureCollection", "features": feats}
    import json
    respx.post(base).mock(return_value=httpx.Response(200, content=json.dumps(payload).encode()))

    client = WFSClient(base_url=base, cache_dir=tmp_path)
    sf = SpatialFilter(
        predicate="intersects",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        geom_property="geom",
    )

    with pytest.raises(TooManyFeaturesError):
        await client.get_features(layer="x", spatial_filter=sf, attribute_filter=None, max_features=5)


@respx.mock
async def test_get_features_ows_exception_raises_wfs_request_error(tmp_path: Path) -> None:
    from geo_agent.services.wfs_client import WFSRequestError

    base = "https://example.test/wfs"
    ows_report = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">'
        b'<ows:Exception exceptionCode="OperationParsingFailed">'
        b'<ows:ExceptionText>Parsing failed for PropertyIsLike</ows:ExceptionText>'
        b'</ows:Exception></ows:ExceptionReport>'
    )
    respx.post(base).mock(return_value=httpx.Response(400, content=ows_report))

    client = WFSClient(base_url=base, cache_dir=tmp_path)
    sf = SpatialFilter(
        predicate="intersects",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        geom_property="geom",
    )

    with pytest.raises(WFSRequestError) as exc_info:
        await client.get_features(
            layer="montreal:arrondissements", spatial_filter=sf, attribute_filter=None, max_features=100
        )
    msg = str(exc_info.value)
    assert "HTTP 400" in msg
    assert "OperationParsingFailed" in msg
