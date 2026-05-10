from __future__ import annotations

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
