from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import dataset_not_found_command, tool_error_command
from geo_agent.agent.registry import get_services
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
) -> dict | Command:
    """Surface a view of a dataset to the user in the chat (does not change the map).

    view:
      "schema"   — attribute names, types, and a sample value from the first feature
      "features" — a compact table of up to 50 features (properties only; no geometry)
      "feature"  — one feature's full properties + a geometry summary; requires feature_index

    Examples:
      {"dataset_id": "result_003", "view": "schema"}
      {"dataset_id": "result_003", "view": "features"}
      {"dataset_id": "result_003", "view": "feature", "feature_index": 0}

    You receive only property values and a geometry-type summary — never the coordinates.

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
        sample = (features[0].get("properties") or {}) if features else {}
        return {
            "view": "schema",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "attribute_schema": meta.attribute_schema,
            "sample": sample,
        }

    if view == "features":
        rows = [
            {
                "index": i,
                "properties": (f.get("properties") or {}),
                "geometry_type": _geometry_type(f),
            }
            for i, f in enumerate(features[:FEATURE_LIST_CAP])
        ]
        return {
            "view": "features",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "total": len(features),
            "features": rows,
        }

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
    return {
        "view": "feature",
        "dataset_id": meta.id,
        "alias": meta.alias,
        "index": feature_index,
        "properties": (f.get("properties") or {}),
        "geometry_type": _geometry_type(f),
        "vertex_count": _vertex_count(f.get("geometry")),
    }
