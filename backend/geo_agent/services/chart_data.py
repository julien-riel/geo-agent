from __future__ import annotations

from collections import Counter
from typing import Literal

from geo_agent.models import ChartData, ChartSeriesPoint
from geo_agent.services.spatial_ops import AggregateOp, aggregate as _aggregate

TOP_N_CAP = 10


def _attribute_exists(geojson: dict, attribute: str) -> bool:
    for f in geojson.get("features", []):
        props = f.get("properties") or {}
        if attribute in props:
            return True
    return False


def top_values_for_chart(
    geojson: dict,
    attribute: str,
    chart_type: Literal["bar", "pie"],
    dataset_id: str,
    dataset_alias: str | None,
) -> ChartData:
    """Frequency of an attribute's values. Skips nulls. Truncates to TOP_N_CAP + 'Autres'."""
    features = geojson.get("features", [])

    if features and not _attribute_exists(geojson, attribute):
        raise KeyError(attribute)

    values = []
    for f in features:
        v = (f.get("properties") or {}).get(attribute)
        if v is not None:
            values.append(v)

    counter = Counter(values)
    ranked = counter.most_common()
    non_null_total = len(values)
    truncated = False
    series: list[ChartSeriesPoint] = []

    if len(ranked) > TOP_N_CAP:
        head = ranked[:TOP_N_CAP]
        tail = ranked[TOP_N_CAP:]
        truncated = True
        for val, count in head:
            series.append(
                ChartSeriesPoint(
                    label=str(val),
                    value=float(count),
                    percent=(count / non_null_total) if non_null_total else None,
                )
            )
        other_count = sum(c for _, c in tail)
        series.append(
            ChartSeriesPoint(
                label="Autres",
                value=float(other_count),
                percent=(other_count / non_null_total) if non_null_total else None,
            )
        )
    else:
        for val, count in ranked:
            series.append(
                ChartSeriesPoint(
                    label=str(val),
                    value=float(count),
                    percent=(count / non_null_total) if non_null_total else None,
                )
            )

    return ChartData(
        chart_type=chart_type,
        title=f"Fréquence — {attribute}",
        dataset_id=dataset_id,
        dataset_alias=dataset_alias,
        source="attribute_distribution",
        attribute=attribute,
        aggregation=None,
        total_features=len(features),
        series=series,
        truncated=truncated,
    )


_ADDITIVE_OPS = {"count", "sum"}


def aggregation_for_chart(
    geojson: dict,
    group_by: str,
    metric: str | None,
    op: AggregateOp,
    dataset_id: str,
    dataset_alias: str | None,
) -> ChartData:
    """Run a grouped aggregation; package as grouped_bar ChartData.

    For additive ops (count, sum), the tail beyond TOP_N_CAP is rolled into an 'Autres' bucket
    and percentages are computed. For mean/min/max, truncation drops the tail without a
    synthetic bucket and percent is None.
    """
    result = _aggregate(geojson, op=op, attribute=metric, group_by=group_by)
    groups = result.get("groups") or []

    # Sort desc by numeric value; None values sort last.
    def _sort_key(g: dict) -> float:
        v = g.get("value")
        return float(v) if isinstance(v, (int, float)) else float("-inf")

    groups_sorted = sorted(groups, key=_sort_key, reverse=True)

    additive = op in _ADDITIVE_OPS
    total = sum(_sort_key(g) for g in groups_sorted if _sort_key(g) != float("-inf")) if additive else 0.0

    truncated = False
    series: list[ChartSeriesPoint] = []
    if len(groups_sorted) > TOP_N_CAP:
        truncated = True
        head = groups_sorted[:TOP_N_CAP]
        tail = groups_sorted[TOP_N_CAP:]
    else:
        head = groups_sorted
        tail = []

    for g in head:
        v = g.get("value")
        if v is None:
            continue
        value = float(v)
        series.append(
            ChartSeriesPoint(
                label=str(g.get("key")),
                value=value,
                percent=(value / total) if (additive and total) else None,
            )
        )

    if tail and additive:
        tail_total = sum(_sort_key(g) for g in tail if _sort_key(g) != float("-inf"))
        series.append(
            ChartSeriesPoint(
                label="Autres",
                value=tail_total,
                percent=(tail_total / total) if total else None,
            )
        )

    title = f"count par {group_by}" if op == "count" else f"{op}({metric}) par {group_by}"

    return ChartData(
        chart_type="grouped_bar",
        title=title,
        dataset_id=dataset_id,
        dataset_alias=dataset_alias,
        source="aggregation",
        attribute=None,
        aggregation={"group_by": group_by, "metric": metric, "op": op},
        total_features=len(geojson.get("features", [])),
        series=series,
        truncated=truncated,
    )
