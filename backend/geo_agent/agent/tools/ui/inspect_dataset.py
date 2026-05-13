from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolCallId
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import (
    dataset_not_found_command,
    inspection_command,
    tool_error_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool
from geo_agent.models import ToolError

FEATURE_LIST_CAP = 50


def _geometry_type(feature: dict) -> str | None:
    return (feature.get("geometry") or {}).get("type")


def _vertex_count(geom: dict | None) -> int:
    if not geom:
        return 0
    if geom.get("type") == "GeometryCollection":
        return sum(_vertex_count(g) for g in geom.get("geometries", []))

    def walk(c: Any) -> int:
        if isinstance(c, (int, float)):
            return 0
        if isinstance(c, list) and len(c) >= 2 and all(isinstance(x, (int, float)) for x in c[:2]):
            return 1
        if isinstance(c, list):
            return sum(walk(x) for x in c)
        return 0

    return walk(geom.get("coordinates"))


@tool
async def inspect_dataset(
    dataset_id: str,
    view: Literal["schema", "features", "feature"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    feature_index: Annotated[
        int | None,
        Field(description="Required for view='feature': 0-based index into the dataset"),
    ] = None,
) -> Command:
    """Render a view of a dataset to the user in the chat (does not change the map).

    view:
      "schema"   — attribute names, types, and a sample value from the first feature
      "features" — a compact table of up to 50 features (properties only; no geometry)
      "feature"  — one feature's full properties + a geometry summary; requires feature_index

    Examples:
      {"dataset_id": "result_003", "view": "schema"}
      {"dataset_id": "result_003", "view": "features"}
      {"dataset_id": "result_003", "view": "feature", "feature_index": 0}

    The view is drawn for the user. You only get back a short confirmation (the view shown and the
    feature counts) — NOT the table itself. If you need attribute names to plan a filter, call
    describe_dataset instead.

    On failure: dataset_not_found (bad dataset_id), bad_input (feature_index out of range).
    """
    services = get_services()
    try:
        meta = services.store.get_meta(dataset_id)
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    features = gj.get("features", [])

    if view == "schema":
        payload = {
            "view": "schema",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "attribute_schema": meta.attribute_schema,
            "sample": (features[0].get("properties") or {}) if features else {},
        }
        summary = {
            "shown_to_user": "schema",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "feature_count": len(features),
        }
        return inspection_command(payload, summary, tool_call_id)

    if view == "features":
        rows = [
            {
                "index": i,
                "properties": (f.get("properties") or {}),
                "geometry_type": _geometry_type(f),
            }
            for i, f in enumerate(features[:FEATURE_LIST_CAP])
        ]
        payload = {
            "view": "features",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "total": len(features),
            "features": rows,
        }
        summary = {
            "shown_to_user": "features",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "feature_count": len(features),
            "rows_shown": len(rows),
        }
        return inspection_command(payload, summary, tool_call_id)

    # view == "feature"
    if feature_index is None or feature_index < 0 or feature_index >= len(features):
        upper = max(len(features) - 1, 0)
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"feature_index out of range (dataset has {len(features)} features)",
                suggestion=f"feature_index must be 0..{upper}",
            ),
            tool_call_id,
        )
    f = features[feature_index]
    payload = {
        "view": "feature",
        "dataset_id": meta.id,
        "alias": meta.alias,
        "index": feature_index,
        "properties": (f.get("properties") or {}),
        "geometry_type": _geometry_type(f),
        "vertex_count": _vertex_count(f.get("geometry")),
    }
    summary = {
        "shown_to_user": "feature",
        "dataset_id": meta.id,
        "alias": meta.alias,
        "feature_index": feature_index,
        "geometry_type": _geometry_type(f),
    }
    return inspection_command(payload, summary, tool_call_id)
