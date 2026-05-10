import pytest

from geo_agent.services.attribute_stats import compute_attribute_stats


def _gj(props_list: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": p}
            for p in props_list
        ],
    }


def test_number_attribute_returns_min_max_distinct() -> None:
    gj = _gj([{"len": 10.0}, {"len": 20.5}, {"len": 10.0}, {"len": None}])
    s = compute_attribute_stats(gj, "len")
    assert s["attribute"] == "len"
    assert s["type"] == "number"
    assert s["non_null_count"] == 3
    assert s["null_count"] == 1
    assert s["distinct_count"] == 2
    assert s["min"] == 10.0
    assert s["max"] == 20.5
    assert "top_values" not in s  # numbers don't get top_values


def test_string_attribute_returns_top_values() -> None:
    gj = _gj([{"k": "A"}, {"k": "B"}, {"k": "A"}, {"k": "A"}, {"k": "C"}])
    s = compute_attribute_stats(gj, "k")
    assert s["type"] == "string"
    assert s["non_null_count"] == 5
    assert s["null_count"] == 0
    assert s["distinct_count"] == 3
    assert s["top_values"][0] == {"value": "A", "count": 3}
    assert {"value": "B", "count": 1} in s["top_values"]
    assert {"value": "C", "count": 1} in s["top_values"]
    assert "min" not in s


def test_boolean_attribute_treated_as_string_like() -> None:
    gj = _gj([{"on": True}, {"on": False}, {"on": True}])
    s = compute_attribute_stats(gj, "on")
    assert s["type"] == "boolean"
    assert s["non_null_count"] == 3
    assert s["distinct_count"] == 2
    assert {"value": True, "count": 2} in s["top_values"]


def test_unknown_attribute_raises_keyerror() -> None:
    gj = _gj([{"a": 1}])
    with pytest.raises(KeyError):
        compute_attribute_stats(gj, "nope")


def test_top_values_caps_at_10() -> None:
    gj = _gj([{"v": str(i % 25)} for i in range(200)])
    s = compute_attribute_stats(gj, "v")
    assert len(s["top_values"]) == 10
    # sorted desc by count
    counts = [t["count"] for t in s["top_values"]]
    assert counts == sorted(counts, reverse=True)
