from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        return datetime.now(timezone.utc) - when < self._ttl

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
        self._mem_fetched_at = datetime.now(timezone.utc)
        return layers
