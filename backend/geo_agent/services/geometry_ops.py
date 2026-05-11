from __future__ import annotations

import json
import math
from typing import Any, Literal

import geopandas as gpd

WGS84 = "EPSG:4326"
MONTREAL_METRIC_CRS = "EPSG:32188"  # NAD83 / MTM zone 8 — Montreal's metric reference

OverlayOp = Literal["intersection", "union", "difference", "clip"]
TransformOp = Literal["buffer", "centroid", "simplify", "dissolve"]
JoinPredicate = Literal["intersects", "within", "contains"]


def _to_gdf(geojson: dict) -> gpd.GeoDataFrame:
    feats = geojson.get("features", [])
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs=WGS84)
    return gpd.GeoDataFrame.from_features(feats, crs=WGS84)


def _clean(obj: Any) -> Any:
    """Replace NaN floats (introduced by left joins / overlays) with None and strip
    numpy scalars so the result is plain JSON-safe Python."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _to_geojson(gdf: gpd.GeoDataFrame) -> dict:
    if len(gdf) == 0:
        return {"type": "FeatureCollection", "features": []}
    return _clean(json.loads(gdf.to_json()))


def overlay(left: dict, right: dict, op: OverlayOp) -> dict:
    """Geometric overlay of two feature collections, returning a new collection.

    intersection / clip — parts of `left` that fall inside `right` (keeps left's attributes,
                          drops features that do not overlap).
    union               — geometric union of both layers' features (attributes from both).
    difference          — `left` minus the parts overlapping `right` (keeps left's attributes).
    """
    left_gdf = _to_gdf(left)
    right_gdf = _to_gdf(right)
    if len(left_gdf) == 0 or len(right_gdf) == 0:
        return {"type": "FeatureCollection", "features": []}
    if op in ("intersection", "clip"):
        out = gpd.clip(left_gdf, right_gdf, keep_geom_type=False)
    elif op in ("union", "difference"):
        out = gpd.overlay(left_gdf, right_gdf, how=op, keep_geom_type=False)
    else:
        raise ValueError(f"unknown overlay op: {op!r}")
    return _to_geojson(out)


def transform(
    geojson: dict,
    op: TransformOp,
    *,
    distance_meters: float | None = None,
    tolerance: float | None = None,
    by: str | None = None,
) -> dict:
    """Single-dataset geometry transformation, returning a new collection.

    buffer    — requires distance_meters (metres); reprojects to EPSG:32188, buffers, reprojects back.
    centroid  — replaces each geometry with its centroid (Point); attributes preserved.
    simplify  — requires tolerance (degrees, since the data is EPSG:4326); Douglas–Peucker.
    dissolve  — merge features; with `by` (attribute name), one feature per distinct value of that
                attribute keeping only that attribute; without `by`, one feature with no attributes.
    """
    gdf = _to_gdf(geojson)
    if len(gdf) == 0:
        return {"type": "FeatureCollection", "features": []}

    if op == "buffer":
        if distance_meters is None:
            raise ValueError("buffer requires distance_meters")
        metric = gdf.to_crs(MONTREAL_METRIC_CRS)
        metric["geometry"] = metric.geometry.buffer(distance_meters)
        out = metric.to_crs(WGS84)
    elif op == "centroid":
        metric = gdf.to_crs(MONTREAL_METRIC_CRS)
        metric["geometry"] = metric.geometry.centroid
        out = metric.to_crs(WGS84)
    elif op == "simplify":
        if tolerance is None:
            raise ValueError("simplify requires tolerance")
        out = gdf.copy()
        out["geometry"] = gdf.geometry.simplify(tolerance, preserve_topology=True)
    elif op == "dissolve":
        if by is None:
            out = gdf[["geometry"]].dissolve().reset_index(drop=True)
        else:
            if by not in gdf.columns:
                raise ValueError(f"dissolve: attribute {by!r} not in dataset")
            out = gdf[[by, "geometry"]].dissolve(by=by).reset_index()
    else:
        raise ValueError(f"unknown transform op: {op!r}")

    return _to_geojson(out)
