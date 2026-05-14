from __future__ import annotations

from collections import Counter
from typing import Literal

from geo_agent.models import ChartData, ChartSeriesPoint

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
