import pytest
from shapely.geometry import shape

from geo_agent.services.geometry_ops import overlay
from geo_agent.services.geometry_ops import transform


def _poly(coords: list, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": props}


def _fc(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def test_overlay_intersection_clips_left_to_right_and_keeps_left_attrs() -> None:
    lines = _fc(
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]}, "properties": {"name": "rue A"}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 5], [10, 5]]}, "properties": {"name": "rue B"}},
    )
    box = _fc(_poly([[2, -1], [4, -1], [4, 1], [2, 1], [2, -1]], zone="z1"))

    out = overlay(lines, box, "intersection")

    assert len(out["features"]) == 1
    f = out["features"][0]
    assert f["properties"]["name"] == "rue A"
    xs = [c[0] for c in f["geometry"]["coordinates"]]
    assert min(xs) >= 1.999 and max(xs) <= 4.001


def test_overlay_clip_is_same_as_intersection() -> None:
    lines = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]}, "properties": {"name": "rue A"}})
    box = _fc(_poly([[2, -1], [4, -1], [4, 1], [2, 1], [2, -1]]))
    assert overlay(lines, box, "clip") == overlay(lines, box, "intersection")


def test_overlay_difference_removes_overlapping_part() -> None:
    a = _fc(_poly([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], id=1))
    b = _fc(_poly([[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], id=2))

    out = overlay(a, b, "difference")

    assert len(out["features"]) == 1
    assert abs(shape(out["features"][0]["geometry"]).area - 50.0) < 0.01


def test_overlay_intersection_empty_when_disjoint() -> None:
    a = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]))
    b = _fc(_poly([[100, 100], [101, 100], [101, 101], [100, 101], [100, 100]]))
    assert overlay(a, b, "intersection")["features"] == []


def test_overlay_empty_when_either_side_empty() -> None:
    a = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]))
    empty = _fc()
    assert overlay(a, empty, "intersection")["features"] == []
    assert overlay(empty, a, "union")["features"] == []


def test_transform_buffer_produces_polygon_with_area_and_keeps_attrs() -> None:
    pt = _fc({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.567, 45.501]}, "properties": {"name": "x"}})
    out = transform(pt, "buffer", distance_meters=100)
    geom = shape(out["features"][0]["geometry"])
    assert geom.geom_type == "Polygon"
    assert geom.area > 0
    assert out["features"][0]["properties"]["name"] == "x"


def test_transform_buffer_requires_distance() -> None:
    pt = _fc({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.567, 45.501]}, "properties": {}})
    with pytest.raises(ValueError):
        transform(pt, "buffer")


def test_transform_centroid_is_point() -> None:
    poly = _fc(_poly([[-73.6, 45.5], [-73.5, 45.5], [-73.5, 45.6], [-73.6, 45.6], [-73.6, 45.5]], k=1))
    out = transform(poly, "centroid")
    assert out["features"][0]["geometry"]["type"] == "Point"
    assert out["features"][0]["properties"]["k"] == 1


def test_transform_simplify_reduces_vertices() -> None:
    line = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0.0000001], [2, 0]]}, "properties": {}})
    out = transform(line, "simplify", tolerance=0.001)
    assert len(out["features"][0]["geometry"]["coordinates"]) == 2


def test_transform_simplify_requires_tolerance() -> None:
    line = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0], [2, 0]]}, "properties": {}})
    with pytest.raises(ValueError):
        transform(line, "simplify")


def test_transform_dissolve_by_attribute_collapses_per_key() -> None:
    fc = _fc(
        _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"),
        _poly([[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]], cat="a"),
        _poly([[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]], cat="b"),
    )
    out = transform(fc, "dissolve", by="cat")
    assert len(out["features"]) == 2
    assert sorted(f["properties"]["cat"] for f in out["features"]) == ["a", "b"]


def test_transform_dissolve_without_by_makes_one_feature() -> None:
    fc = _fc(
        _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"),
        _poly([[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]], cat="b"),
    )
    out = transform(fc, "dissolve")
    assert len(out["features"]) == 1


def test_transform_dissolve_unknown_attribute_raises() -> None:
    fc = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"))
    with pytest.raises(ValueError):
        transform(fc, "dissolve", by="nope")
