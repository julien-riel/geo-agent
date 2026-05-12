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


def test_build_filter_polygon_with_hole_emits_interior_ring() -> None:
    polygon_with_hole = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]],
        ],
    }
    sf = SpatialFilter(predicate="intersects", geometry=polygon_with_hole, geom_property="geom")
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    polygon = root.find("fes:Intersects/gml:Polygon", NS)
    assert polygon is not None
    assert polygon.find("gml:exterior", NS) is not None
    interior = polygon.find("gml:interior", NS)
    assert interior is not None
    poslist = interior.find("gml:LinearRing/gml:posList", NS)
    assert poslist is not None and poslist.text == "2 2 4 2 4 4 2 4 2 2"


def test_build_filter_intersects_multipolygon_emits_multisurface() -> None:
    multipolygon = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]], [[5.2, 5.2], [5.4, 5.2], [5.4, 5.4], [5.2, 5.4], [5.2, 5.2]]],
        ],
    }
    sf = SpatialFilter(predicate="within", geometry=multipolygon, geom_property="geom")
    xml = build_filter(spatial=sf, attributes=None)
    root = etree.fromstring(xml.encode("utf-8"))
    within = root.find("fes:Within", NS)
    assert within is not None
    ms = within.find("gml:MultiSurface", NS)
    assert ms is not None
    members = ms.findall("gml:surfaceMember", NS)
    assert len(members) == 2
    assert members[0].find("gml:Polygon", NS) is not None
    # second member has a hole → its Polygon carries an interior ring
    second_polygon = members[1].find("gml:Polygon", NS)
    assert second_polygon is not None
    assert second_polygon.find("gml:interior", NS) is not None


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


def test_build_filter_like_emits_required_wildcard_attributes() -> None:
    af = AttributeFilter(property="nom", op="like", value="%Baldwin%")
    xml = build_filter(spatial=None, attributes=af)
    root = etree.fromstring(xml.encode("utf-8"))
    like = root.find("fes:PropertyIsLike", NS)
    assert like is not None
    # FES 2.0 requires wildCard / singleChar / escapeChar on PropertyIsLike
    assert like.get("wildCard") == "%"
    assert like.get("singleChar") == "_"
    assert like.get("escapeChar") == "\\"
    assert like.get("matchCase") == "false"
    assert like.find("fes:ValueReference", NS).text == "nom"
    assert like.find("fes:Literal", NS).text == "%Baldwin%"
