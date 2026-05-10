from collections import Counter
from typing import Any


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def compute_attribute_stats(geojson: dict, attribute: str) -> dict:
    """Compute summary stats for one attribute across all features.

    Raises KeyError if no feature carries the attribute (even with a null value).
    """
    values: list[Any] = []
    null_count = 0
    found = False
    for feat in geojson.get("features", []):
        props = feat.get("properties") or {}
        if attribute not in props:
            continue
        found = True
        v = props[attribute]
        if v is None:
            null_count += 1
        else:
            values.append(v)

    if not found:
        raise KeyError(attribute)

    non_null_count = len(values)
    distinct_count = len(set(values)) if values else 0

    inferred = _infer_type(values[0]) if values else "string"

    out: dict[str, Any] = {
        "attribute": attribute,
        "type": inferred,
        "non_null_count": non_null_count,
        "null_count": null_count,
        "distinct_count": distinct_count,
    }

    if inferred == "number" and values:
        out["min"] = min(values)
        out["max"] = max(values)
    else:
        counter = Counter(values)
        out["top_values"] = [
            {"value": v, "count": c} for v, c in counter.most_common(10)
        ]

    return out
