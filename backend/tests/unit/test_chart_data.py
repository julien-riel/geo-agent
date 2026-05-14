import pytest

from geo_agent.services.chart_data import top_values_for_chart


def _gj(props_list: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None, "properties": p}
            for p in props_list
        ],
    }


def test_top_values_basic_bar() -> None:
    gj = _gj([{"k": "A"}, {"k": "B"}, {"k": "A"}, {"k": "A"}, {"k": "C"}])
    cd = top_values_for_chart(gj, "k", "bar", dataset_id="d1", dataset_alias="ds")
    assert cd.chart_type == "bar"
    assert cd.title == "Fréquence — k"
    assert cd.source == "attribute_distribution"
    assert cd.attribute == "k"
    assert cd.aggregation is None
    assert cd.total_features == 5
    assert cd.dataset_alias == "ds"
    labels = [p.label for p in cd.series]
    values = [p.value for p in cd.series]
    assert labels == ["A", "B", "C"]
    assert values == [3.0, 1.0, 1.0]
    assert cd.series[0].percent == pytest.approx(0.6)
    assert cd.truncated is False


def test_top_values_pie_same_data_different_chart_type() -> None:
    gj = _gj([{"k": "A"}, {"k": "B"}])
    cd = top_values_for_chart(gj, "k", "pie", dataset_id="d1", dataset_alias=None)
    assert cd.chart_type == "pie"


def test_top_values_truncates_to_top_n_with_other_bucket() -> None:
    # 12 distinct values, one with count 5, rest with 1 each. Expect top 10 + Autres.
    props = [{"k": "TOP"}] * 5 + [{"k": f"v{i}"} for i in range(11)]
    gj = _gj(props)
    cd = top_values_for_chart(gj, "k", "bar", dataset_id="d1", dataset_alias=None)
    assert cd.truncated is True
    assert len(cd.series) == 11  # 10 real + Autres
    assert cd.series[-1].label == "Autres"
    # TOP + 9 of the singletons = 14 features included in top 10; 2 land in Autres
    assert cd.series[-1].value == 2.0


def test_top_values_skips_nulls_and_uses_non_null_total_for_percent() -> None:
    gj = _gj([{"k": "A"}, {"k": "A"}, {"k": None}, {"k": None}])
    cd = top_values_for_chart(gj, "k", "bar", dataset_id="d1", dataset_alias=None)
    assert cd.series[0].percent == pytest.approx(1.0)
    assert cd.total_features == 4


def test_top_values_empty_dataset_returns_empty_series() -> None:
    cd = top_values_for_chart(_gj([]), "k", "bar", dataset_id="d1", dataset_alias=None)
    assert cd.series == []
    assert cd.total_features == 0
    assert cd.truncated is False


def test_top_values_all_null_returns_empty_series() -> None:
    gj = _gj([{"k": None}, {"k": None}])
    cd = top_values_for_chart(gj, "k", "bar", dataset_id="d1", dataset_alias=None)
    assert cd.series == []
    assert cd.total_features == 2


def test_top_values_unknown_attribute_raises_keyerror() -> None:
    gj = _gj([{"a": 1}])
    with pytest.raises(KeyError):
        top_values_for_chart(gj, "nope", "bar", dataset_id="d1", dataset_alias=None)


def test_top_values_boolean_labels_stringified() -> None:
    gj = _gj([{"on": True}, {"on": False}, {"on": True}])
    cd = top_values_for_chart(gj, "on", "bar", dataset_id="d1", dataset_alias=None)
    labels = [p.label for p in cd.series]
    assert set(labels) == {"True", "False"}
