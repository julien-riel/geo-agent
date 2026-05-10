from collections import defaultdict
from typing import Any, Literal

AggregateOp = Literal["count", "sum", "mean", "min", "max"]


def _values(features: list[dict], attribute: str | None) -> list[Any]:
    if attribute is None:
        return [None] * len(features)
    out = []
    for f in features:
        v = (f.get("properties") or {}).get(attribute)
        if v is None:
            continue
        out.append(v)
    return out


def _apply_op(op: AggregateOp, values: list[Any], features_count: int) -> Any:
    if op == "count":
        return features_count
    if not values:
        return None
    if op == "sum":
        return sum(values)
    if op == "mean":
        return sum(values) / len(values)
    if op == "min":
        return min(values)
    if op == "max":
        return max(values)
    raise ValueError(f"Unknown op: {op}")


def aggregate(
    geojson: dict,
    op: AggregateOp,
    attribute: str | None,
    group_by: str | None,
) -> dict:
    if op not in ("count", "sum", "mean", "min", "max"):
        raise ValueError(f"Unsupported op: {op}")
    if op != "count" and attribute is None:
        raise ValueError(f"op '{op}' requires an attribute")

    features = geojson.get("features", [])

    if group_by is None:
        values = _values(features, attribute) if attribute else []
        return {"value": _apply_op(op, values, len(features))}

    groups: dict[Any, list[dict]] = defaultdict(list)
    for f in features:
        key = (f.get("properties") or {}).get(group_by)
        groups[key].append(f)

    out = []
    for key, feats in groups.items():
        values = _values(feats, attribute) if attribute else []
        out.append({"key": key, "value": _apply_op(op, values, len(feats))})

    return {"value": None, "groups": out}


def filter_by_attribute(geojson: dict, predicate: str) -> dict:
    """Placeholder — implemented in Task 13."""
    raise NotImplementedError
