import pytest

from geo_agent.services.spatial_ops import (
    AggregateOp,
    AttributePredicate,
    aggregate,
    filter_by_attribute,
)


@pytest.fixture
def sample_fc() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None, "properties": {"type": "rue", "longueur": 100}},
            {"type": "Feature", "geometry": None, "properties": {"type": "rue", "longueur": 250}},
            {"type": "Feature", "geometry": None, "properties": {"type": "boulevard", "longueur": 1000}},
            {"type": "Feature", "geometry": None, "properties": {"type": "boulevard", "longueur": 500}},
        ],
    }


def test_aggregate_count(sample_fc: dict) -> None:
    r = aggregate(sample_fc, op="count", attribute=None, group_by=None)
    assert r == {"value": 4}


def test_aggregate_sum(sample_fc: dict) -> None:
    r = aggregate(sample_fc, op="sum", attribute="longueur", group_by=None)
    assert r == {"value": 1850}


def test_aggregate_mean(sample_fc: dict) -> None:
    r = aggregate(sample_fc, op="mean", attribute="longueur", group_by=None)
    assert r == {"value": 462.5}


def test_aggregate_min_max(sample_fc: dict) -> None:
    assert aggregate(sample_fc, op="min", attribute="longueur", group_by=None) == {"value": 100}
    assert aggregate(sample_fc, op="max", attribute="longueur", group_by=None) == {"value": 1000}


def test_aggregate_with_group_by(sample_fc: dict) -> None:
    r = aggregate(sample_fc, op="sum", attribute="longueur", group_by="type")
    assert r["value"] is None
    groups = {g["key"]: g["value"] for g in r["groups"]}
    assert groups == {"rue": 350, "boulevard": 1500}


def test_aggregate_count_with_group_by(sample_fc: dict) -> None:
    r = aggregate(sample_fc, op="count", attribute=None, group_by="type")
    groups = {g["key"]: g["value"] for g in r["groups"]}
    assert groups == {"rue": 2, "boulevard": 2}


def test_aggregate_empty_collection() -> None:
    r = aggregate({"type": "FeatureCollection", "features": []}, op="count", attribute=None, group_by=None)
    assert r == {"value": 0}


def test_aggregate_invalid_op_raises() -> None:
    with pytest.raises(ValueError):
        aggregate({"type": "FeatureCollection", "features": []}, op="median", attribute="x", group_by=None)  # type: ignore[arg-type]


def test_aggregate_sum_requires_attribute() -> None:
    with pytest.raises(ValueError):
        aggregate({"type": "FeatureCollection", "features": []}, op="sum", attribute=None, group_by=None)


def test_filter_by_attribute_eq(sample_fc: dict) -> None:
    pred = AttributePredicate(property="type", op="eq", value="rue")
    out = filter_by_attribute(sample_fc, pred)
    assert len(out["features"]) == 2
    assert all(f["properties"]["type"] == "rue" for f in out["features"])


def test_filter_by_attribute_gt(sample_fc: dict) -> None:
    pred = AttributePredicate(property="longueur", op="gt", value=300)
    out = filter_by_attribute(sample_fc, pred)
    assert len(out["features"]) == 2
    assert all(f["properties"]["longueur"] > 300 for f in out["features"])


def test_filter_by_attribute_in(sample_fc: dict) -> None:
    pred = AttributePredicate(property="type", op="in", value=["rue", "ruelle"])
    out = filter_by_attribute(sample_fc, pred)
    assert len(out["features"]) == 2


def test_filter_by_attribute_preserves_structure(sample_fc: dict) -> None:
    pred = AttributePredicate(property="type", op="eq", value="boulevard")
    out = filter_by_attribute(sample_fc, pred)
    assert out["type"] == "FeatureCollection"
