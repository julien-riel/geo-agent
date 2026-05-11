import pytest
from shapely.geometry import shape

from geo_agent.services.geometry_ops import overlay


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
