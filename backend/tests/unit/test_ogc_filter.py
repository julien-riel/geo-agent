from lxml import etree

from geo_agent.services.ogc_filter import (
    AttributeFilter,
    SpatialFilter,
    build_filter,
)

NS = {"fes": "http://www.opengis.net/fes/2.0", "gml": "http://www.opengis.net/gml/3.2"}


def _polygon_geojson() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [[-73.7, 45.4], [-73.5, 45.4], [-73.5, 45.6], [-73.7, 45.6], [-73.7, 45.4]]
        ],
    }


def test_build_filter_intersects_polygon() -> None:
    sf = SpatialFilter(predicate="intersects", geometry=_polygon_geojson(), geom_property="geom")
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag == "{http://www.opengis.net/fes/2.0}Filter"
    intersects = root.find("fes:Intersects", NS)
    assert intersects is not None
    valref = intersects.find("fes:ValueReference", NS)
    assert valref is not None and valref.text == "geom"
    polygon = intersects.find("gml:Polygon", NS)
    assert polygon is not None


def test_build_filter_within_predicate() -> None:
    sf = SpatialFilter(predicate="within", geometry=_polygon_geojson(), geom_property="the_geom")
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find("fes:Within", NS) is not None


def test_build_filter_bbox() -> None:
    sf = SpatialFilter(
        predicate="bbox",
        geometry={"type": "Envelope", "bbox": [-73.7, 45.4, -73.5, 45.6]},
        geom_property="geom",
    )
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    bbox = root.find("fes:BBOX", NS)
    assert bbox is not None
    env = bbox.find("gml:Envelope", NS)
    assert env is not None


def test_build_filter_dwithin_with_distance() -> None:
    sf = SpatialFilter(
        predicate="dwithin",
        geometry={"type": "Point", "coordinates": [-73.6, 45.5]},
        geom_property="geom",
        distance_meters=100,
    )
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    dwithin = root.find("fes:DWithin", NS)
    assert dwithin is not None
    dist = dwithin.find("fes:Distance", NS)
    assert dist is not None
    assert dist.get("uom") == "metre"
    assert dist.text == "100"


def test_build_filter_attribute_only() -> None:
    af = AttributeFilter(property="longueur_m", op="gt", value=100)
    xml = build_filter(spatial=None, attributes=af)
    root = etree.fromstring(xml.encode("utf-8"))
    gt = root.find("fes:PropertyIsGreaterThan", NS)
    assert gt is not None
    valref = gt.find("fes:ValueReference", NS)
    literal = gt.find("fes:Literal", NS)
    assert valref.text == "longueur_m"
    assert literal.text == "100"


def test_build_filter_combined_uses_and() -> None:
    sf = SpatialFilter(predicate="intersects", geometry=_polygon_geojson(), geom_property="geom")
    af = AttributeFilter(property="type", op="eq", value="boulevard")
    xml = build_filter(spatial=sf, attributes=af)
    root = etree.fromstring(xml.encode("utf-8"))
    and_el = root.find("fes:And", NS)
    assert and_el is not None
    assert and_el.find("fes:Intersects", NS) is not None
    assert and_el.find("fes:PropertyIsEqualTo", NS) is not None


def test_build_filter_like_sets_required_wildcard_attributes() -> None:
    af = AttributeFilter(property="nomArrond", op="like", value="%Lasalle%")
    xml = build_filter(spatial=None, attributes=af)
    root = etree.fromstring(xml.encode("utf-8"))
    like = root.find("fes:PropertyIsLike", NS)
    assert like is not None
    assert like.get("wildCard") == "%"
    assert like.get("singleChar") == "_"
    assert like.get("escapeChar") == "\\"
    assert like.find("fes:ValueReference", NS).text == "nomArrond"
    assert like.find("fes:Literal", NS).text == "%Lasalle%"


def test_build_filter_non_like_ops_have_no_wildcard_attributes() -> None:
    af = AttributeFilter(property="type", op="eq", value="parc")
    xml = build_filter(spatial=None, attributes=af)
    root = etree.fromstring(xml.encode("utf-8"))
    eq = root.find("fes:PropertyIsEqualTo", NS)
    assert eq is not None
    assert eq.get("wildCard") is None


def test_build_filter_attribute_ops() -> None:
    cases = {
        "eq": "PropertyIsEqualTo",
        "neq": "PropertyIsNotEqualTo",
        "lt": "PropertyIsLessThan",
        "gt": "PropertyIsGreaterThan",
        "lte": "PropertyIsLessThanOrEqualTo",
        "gte": "PropertyIsGreaterThanOrEqualTo",
        "like": "PropertyIsLike",
    }
    for op, tag in cases.items():
        xml = build_filter(spatial=None, attributes=AttributeFilter(property="x", op=op, value="y"))  # type: ignore[arg-type]
        root = etree.fromstring(xml.encode("utf-8"))
        assert root.find(f"fes:{tag}", NS) is not None, op
