from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel

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


FilterOp = Literal["eq", "neq", "lt", "gt", "lte", "gte", "in"]


class AttributePredicate(BaseModel):
    property: str
    op: FilterOp
    value: Any


def _matches(value: Any, op: FilterOp, target: Any) -> bool:
    if op == "eq":
        return value == target
    if op == "neq":
        return value != target
    if op == "lt":
        return value is not None and value < target
    if op == "gt":
        return value is not None and value > target
    if op == "lte":
        return value is not None and value <= target
    if op == "gte":
        return value is not None and value >= target
    if op == "in":
        return value in (target or [])
    raise ValueError(f"Unsupported op: {op}")


def filter_by_attribute(geojson: dict, predicate: AttributePredicate) -> dict:
    out_features = []
    for f in geojson.get("features", []):
        v = (f.get("properties") or {}).get(predicate.property)
        if _matches(v, predicate.op, predicate.value):
            out_features.append(f)
    return {"type": "FeatureCollection", "features": out_features}
