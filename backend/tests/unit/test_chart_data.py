import pytest

from geo_agent.services.chart_data import aggregation_for_chart, top_values_for_chart


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


def test_aggregation_count_grouped_basic() -> None:
    gj = _gj([{"t": "a"}, {"t": "a"}, {"t": "b"}])
    cd = aggregation_for_chart(
        gj, group_by="t", metric=None, op="count",
        dataset_id="d1", dataset_alias="ds",
    )
    assert cd.chart_type == "grouped_bar"
    assert cd.source == "aggregation"
    assert cd.aggregation == {"group_by": "t", "metric": None, "op": "count"}
    assert cd.title == "count par t"
    labels = [p.label for p in cd.series]
    values = [p.value for p in cd.series]
    assert labels[0] == "a" and values[0] == 2.0
    assert labels[1] == "b" and values[1] == 1.0
    assert cd.series[0].percent == pytest.approx(2 / 3)


def test_aggregation_sum_with_metric_title() -> None:
    gj = _gj([{"t": "a", "v": 10}, {"t": "a", "v": 5}, {"t": "b", "v": 1}])
    cd = aggregation_for_chart(
        gj, group_by="t", metric="v", op="sum",
        dataset_id="d1", dataset_alias=None,
    )
    assert cd.title == "sum(v) par t"
    values = {p.label: p.value for p in cd.series}
    assert values == {"a": 15.0, "b": 1.0}
    assert cd.series[0].percent == pytest.approx(15 / 16)


def test_aggregation_truncation_with_other_for_sum() -> None:
    # 12 groups, group 'big' has 100, rest have 1 each. Top 10 + Autres.
    props = [{"t": "big", "v": 100}] + [{"t": f"g{i}", "v": 1} for i in range(11)]
    gj = _gj(props)
    cd = aggregation_for_chart(
        gj, group_by="t", metric="v", op="sum",
        dataset_id="d1", dataset_alias=None,
    )
    assert cd.truncated is True
    assert cd.series[-1].label == "Autres"
    # 'big' + 9 singletons = 10 in head; 2 singletons land in Autres.
    assert cd.series[-1].value == 2.0


def test_aggregation_truncation_for_mean_has_no_other_bucket() -> None:
    # 12 groups; mean has no meaningful rollup. Truncate without "Autres".
    props = [{"t": f"g{i}", "v": float(i)} for i in range(12)]
    gj = _gj(props)
    cd = aggregation_for_chart(
        gj, group_by="t", metric="v", op="mean",
        dataset_id="d1", dataset_alias=None,
    )
    assert cd.truncated is True
    assert len(cd.series) == 10
    assert all(p.label != "Autres" for p in cd.series)
    # mean is non-additive: percent is None for every point
    assert all(p.percent is None for p in cd.series)


def test_aggregation_empty_dataset_returns_empty_series() -> None:
    cd = aggregation_for_chart(
        _gj([]), group_by="t", metric=None, op="count",
        dataset_id="d1", dataset_alias=None,
    )
    assert cd.series == []
    assert cd.total_features == 0
