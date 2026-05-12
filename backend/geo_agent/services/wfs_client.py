from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from lxml import etree

from geo_agent.models import WFSLayer

WFS_NS = "http://www.opengis.net/wfs/2.0"
OWS_NS = "http://www.opengis.net/ows/1.1"
NSMAP = {"wfs": WFS_NS, "ows": OWS_NS}


def parse_capabilities(xml_bytes: bytes) -> list[WFSLayer]:
    root = etree.fromstring(xml_bytes)
    layers: list[WFSLayer] = []
    for ft in root.iter(f"{{{WFS_NS}}}FeatureType"):
        name_el = ft.find(f"{{{WFS_NS}}}Name")
        title_el = ft.find(f"{{{WFS_NS}}}Title")
        abstract_el = ft.find(f"{{{WFS_NS}}}Abstract")
        crs_el = ft.find(f"{{{WFS_NS}}}DefaultCRS")
        bbox_el = ft.find(f"{{{OWS_NS}}}WGS84BoundingBox")

        if name_el is None or name_el.text is None:
            continue

        bbox: tuple[float, float, float, float] | None = None
        if bbox_el is not None:
            lc = bbox_el.find(f"{{{OWS_NS}}}LowerCorner")
            uc = bbox_el.find(f"{{{OWS_NS}}}UpperCorner")
            if lc is not None and uc is not None and lc.text and uc.text:
                minx, miny = (float(x) for x in lc.text.split())
                maxx, maxy = (float(x) for x in uc.text.split())
                bbox = (minx, miny, maxx, maxy)

        layers.append(
            WFSLayer(
                name=name_el.text,
                title=(title_el.text if title_el is not None else name_el.text) or name_el.text,
                abstract=abstract_el.text if abstract_el is not None else None,
                default_crs=(crs_el.text if crs_el is not None else "EPSG:4326") or "EPSG:4326",
                bbox=bbox,
            )
        )
    return layers


class WFSClient:
    def __init__(
        self,
        base_url: str,
        cache_dir: Path,
        http_timeout_seconds: int = 30,
        capabilities_ttl_seconds: int = 3600,
    ) -> None:
        self._base_url = base_url
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._timeout = http_timeout_seconds
        self._ttl = timedelta(seconds=capabilities_ttl_seconds)
        self._cap_xml_path = cache_dir / "wfs_capabilities_cache.xml"
        self._mem_layers: list[WFSLayer] | None = None
        self._mem_fetched_at: datetime | None = None

    def _is_fresh(self, when: datetime) -> bool:
        return datetime.now(UTC) - when < self._ttl

    async def _fetch_capabilities(self) -> bytes:
        params = {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(self._base_url, params=params)
            r.raise_for_status()
            return r.content

    async def get_layers(self) -> list[WFSLayer]:
        if self._mem_layers is not None and self._mem_fetched_at and self._is_fresh(self._mem_fetched_at):
            return self._mem_layers

        if self._cap_xml_path.exists():
            xml = self._cap_xml_path.read_bytes()
        else:
            xml = await self._fetch_capabilities()
            self._cap_xml_path.write_bytes(xml)

        layers = parse_capabilities(xml)
        self._mem_layers = layers
        self._mem_fetched_at = datetime.now(UTC)
        return layers


XSD_NS = "http://www.w3.org/2001/XMLSchema"

_XSD_TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "double": "number",
    "float": "number",
    "decimal": "number",
    "int": "number",
    "integer": "number",
    "long": "number",
    "short": "number",
    "date": "string",
    "dateTime": "string",
}


@dataclass
class FeatureTypeSchema:
    type_name: str
    geom_property: str
    attribute_schema: dict[str, str]


def parse_describe_feature_type(xml_bytes: bytes, type_name: str) -> FeatureTypeSchema:
    root = etree.fromstring(xml_bytes)
    elements = root.findall(f".//{{{XSD_NS}}}element")

    geom_property = "geom"
    attrs: dict[str, str] = {}
    for el in elements:
        name = el.get("name")
        type_attr = el.get("type", "")
        if not name or not type_attr:
            continue
        # Geometry properties have type like gml:GeometryPropertyType, gml:PointPropertyType, etc.
        if type_attr.startswith("gml:") and "Property" in type_attr:
            geom_property = name
            continue
        # Strip xsd: prefix if present
        local_type = type_attr.split(":")[-1]
        mapped = _XSD_TYPE_MAP.get(local_type, "string")
        attrs[name] = mapped

    return FeatureTypeSchema(type_name=type_name, geom_property=geom_property, attribute_schema=attrs)


async def _describe_feature_type(self: WFSClient, type_name: str) -> FeatureTypeSchema:
    cache_path = self._cache_dir / f"describe_{type_name.replace(':', '_')}.xml"
    if cache_path.exists():
        xml = cache_path.read_bytes()
    else:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "DescribeFeatureType",
            "typeName": type_name,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(self._base_url, params=params)
            r.raise_for_status()
            xml = r.content
            cache_path.write_bytes(xml)
    return parse_describe_feature_type(xml, type_name)


WFSClient.describe_feature_type = _describe_feature_type  # type: ignore[attr-defined]


import json as _json

from geo_agent.services.ogc_filter import (
    AttributeFilter,
    SpatialFilter,
    build_filter,
)


class TooManyFeaturesError(Exception):
    def __init__(self, limit: int):
        super().__init__(
            f"WFS query returned more than {limit} features. Refine the geometry filter "
            f"or add an attribute filter to narrow the result."
        )
        self.limit = limit


def _build_get_feature_xml(
    layer: str,
    filter_xml: str,
    max_features: int,
    srs_name: str = "EPSG:4326",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                service="WFS" version="2.0.0"
                count="{max_features + 1}"
                outputFormat="application/json">
  <wfs:Query typeNames="{layer}" srsName="{srs_name}">
    {filter_xml}
  </wfs:Query>
</wfs:GetFeature>"""


async def _get_features(
    self: WFSClient,
    layer: str,
    spatial_filter: SpatialFilter | None,
    attribute_filter: AttributeFilter | None,
    max_features: int,
) -> dict:
    if spatial_filter is None and attribute_filter is None:
        filter_xml = ""  # whole-layer query, no <fes:Filter>
    else:
        filter_xml = build_filter(spatial=spatial_filter, attributes=attribute_filter)
    body = _build_get_feature_xml(layer, filter_xml, max_features)
    headers = {"Content-Type": "application/xml"}

    async with httpx.AsyncClient(timeout=self._timeout) as client:
        r = await client.post(self._base_url, content=body.encode("utf-8"), headers=headers)
        r.raise_for_status()
        gj = _json.loads(r.content)

    features = gj.get("features", [])
    if len(features) > max_features:
        raise TooManyFeaturesError(max_features)
    return gj


WFSClient.get_features = _get_features  # type: ignore[attr-defined]
