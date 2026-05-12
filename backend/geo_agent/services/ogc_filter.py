from typing import Any, Literal

from lxml import etree
from pydantic import BaseModel

FES_NS = "http://www.opengis.net/fes/2.0"
GML_NS = "http://www.opengis.net/gml/3.2"
NSMAP = {"fes": FES_NS, "gml": GML_NS}

SpatialPredicate = Literal["intersects", "within", "contains", "bbox", "dwithin"]
AttrOp = Literal["eq", "neq", "lt", "gt", "lte", "gte", "like"]

_OP_TAG = {
    "eq": "PropertyIsEqualTo",
    "neq": "PropertyIsNotEqualTo",
    "lt": "PropertyIsLessThan",
    "gt": "PropertyIsGreaterThan",
    "lte": "PropertyIsLessThanOrEqualTo",
    "gte": "PropertyIsGreaterThanOrEqualTo",
    "like": "PropertyIsLike",
}

_PREDICATE_TAG = {
    "intersects": "Intersects",
    "within": "Within",
    "contains": "Contains",
    "bbox": "BBOX",
    "dwithin": "DWithin",
}


class SpatialFilter(BaseModel):
    predicate: SpatialPredicate
    geometry: dict[str, Any]
    geom_property: str
    distance_meters: float | None = None  # only for dwithin


class AttributeFilter(BaseModel):
    property: str
    op: AttrOp
    value: Any


def _coords_to_pos_list(ring: list[list[float]]) -> str:
    return " ".join(f"{c[0]} {c[1]}" for c in ring)


def _ring_element(parent_tag: str, ring: list[list[float]]) -> etree._Element:
    el = etree.Element(f"{{{GML_NS}}}{parent_tag}", nsmap={"gml": GML_NS})
    linear_ring = etree.SubElement(el, f"{{{GML_NS}}}LinearRing")
    poslist = etree.SubElement(linear_ring, f"{{{GML_NS}}}posList")
    poslist.text = _coords_to_pos_list(ring)
    return el


def _polygon_to_gml(polygon: dict, srs: str = "EPSG:4326") -> etree._Element:
    rings = polygon["coordinates"]
    p = etree.Element(f"{{{GML_NS}}}Polygon", nsmap={"gml": GML_NS})
    p.set("srsName", srs)
    p.append(_ring_element("exterior", rings[0]))
    for hole in rings[1:]:
        p.append(_ring_element("interior", hole))
    return p


def _multipolygon_to_gml(multipolygon: dict, srs: str = "EPSG:4326") -> etree._Element:
    ms = etree.Element(f"{{{GML_NS}}}MultiSurface", nsmap={"gml": GML_NS})
    ms.set("srsName", srs)
    for polygon_rings in multipolygon["coordinates"]:
        member = etree.SubElement(ms, f"{{{GML_NS}}}surfaceMember")
        member.append(_polygon_to_gml({"type": "Polygon", "coordinates": polygon_rings}, srs))
    return ms


def _envelope_to_gml(bbox: list[float], srs: str = "EPSG:4326") -> etree._Element:
    minx, miny, maxx, maxy = bbox
    env = etree.Element(f"{{{GML_NS}}}Envelope", nsmap={"gml": GML_NS})
    env.set("srsName", srs)
    lc = etree.SubElement(env, f"{{{GML_NS}}}lowerCorner")
    lc.text = f"{minx} {miny}"
    uc = etree.SubElement(env, f"{{{GML_NS}}}upperCorner")
    uc.text = f"{maxx} {maxy}"
    return env


def _point_to_gml(point: dict, srs: str = "EPSG:4326") -> etree._Element:
    p = etree.Element(f"{{{GML_NS}}}Point", nsmap={"gml": GML_NS})
    p.set("srsName", srs)
    pos = etree.SubElement(p, f"{{{GML_NS}}}pos")
    pos.text = f"{point['coordinates'][0]} {point['coordinates'][1]}"
    return p


def _geom_to_gml(geom: dict) -> etree._Element:
    t = geom.get("type")
    if t == "Polygon":
        return _polygon_to_gml(geom)
    if t == "MultiPolygon":
        return _multipolygon_to_gml(geom)
    if t == "Envelope":
        return _envelope_to_gml(geom["bbox"])
    if t == "Point":
        return _point_to_gml(geom)
    raise ValueError(f"Unsupported geometry type for filter: {t}")


def _spatial_element(sf: SpatialFilter) -> etree._Element:
    tag = _PREDICATE_TAG[sf.predicate]
    el = etree.Element(f"{{{FES_NS}}}{tag}", nsmap=NSMAP)

    if sf.predicate == "bbox":
        # BBOX takes ValueReference + Envelope, no inner geometry transform
        valref = etree.SubElement(el, f"{{{FES_NS}}}ValueReference")
        valref.text = sf.geom_property
        env = _envelope_to_gml(sf.geometry["bbox"])
        el.append(env)
        return el

    valref = etree.SubElement(el, f"{{{FES_NS}}}ValueReference")
    valref.text = sf.geom_property
    el.append(_geom_to_gml(sf.geometry))

    if sf.predicate == "dwithin":
        if sf.distance_meters is None:
            raise ValueError("dwithin requires distance_meters")
        dist = etree.SubElement(el, f"{{{FES_NS}}}Distance")
        dist.set("uom", "metre")
        dist.text = str(int(sf.distance_meters)) if float(sf.distance_meters).is_integer() else str(sf.distance_meters)

    return el


def _attribute_element(af: AttributeFilter) -> etree._Element:
    tag = _OP_TAG[af.op]
    el = etree.Element(f"{{{FES_NS}}}{tag}", nsmap=NSMAP)
    if af.op == "like":
        # FES 2.0 requires these on PropertyIsLike; matchCase=false makes name
        # lookups (e.g. %Baldwin%) tolerant of case differences in the data.
        el.set("wildCard", "%")
        el.set("singleChar", "_")
        el.set("escapeChar", "\\")
        el.set("matchCase", "false")
    valref = etree.SubElement(el, f"{{{FES_NS}}}ValueReference")
    valref.text = af.property
    literal = etree.SubElement(el, f"{{{FES_NS}}}Literal")
    literal.text = str(af.value)
    return el


def build_filter(
    spatial: SpatialFilter | None,
    attributes: AttributeFilter | None,
) -> str:
    if spatial is None and attributes is None:
        raise ValueError("At least one of spatial or attributes must be provided")

    root = etree.Element(f"{{{FES_NS}}}Filter", nsmap=NSMAP)
    if spatial is not None and attributes is not None:
        and_el = etree.SubElement(root, f"{{{FES_NS}}}And")
        and_el.append(_spatial_element(spatial))
        and_el.append(_attribute_element(attributes))
    elif spatial is not None:
        root.append(_spatial_element(spatial))
    else:
        assert attributes is not None
        root.append(_attribute_element(attributes))

    return etree.tostring(root, pretty_print=False).decode("utf-8")
