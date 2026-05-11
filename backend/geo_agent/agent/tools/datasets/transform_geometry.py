from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import (
    dataset_created_command,
    dataset_not_found_command,
    tool_error_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.geometry_ops import transform as do_transform

# Metres per degree of latitude near Montreal (~45.5°N). Good enough to let the model
# express a simplification tolerance in metres instead of CRS degrees.
_METRES_PER_DEGREE = 111_320.0

# For each op: the extra parameter it consumes. Any *other* extra parameter being set
# is a sign the model is confused — we reject it rather than silently ignoring it.
_EXTRA_PARAM_BY_OP = {
    "buffer": "distance_meters",
    "centroid": None,
    "simplify": "tolerance_meters",
    "dissolve": "by",  # optional for dissolve, required for the others
}


def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )


@tool
async def transform_geometry(
    dataset_id: str,
    op: Literal["buffer", "centroid", "simplify", "dissolve"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    distance_meters: Annotated[
        float | None,
        Field(description="op='buffer' only: buffer radius in metres"),
    ] = None,
    tolerance_meters: Annotated[
        float | None,
        Field(description="op='simplify' only: simplification tolerance in metres, e.g. 5"),
    ] = None,
    by: Annotated[
        str | None,
        Field(description="op='dissolve' only: attribute to merge by; omit to merge everything"),
    ] = None,
    alias: Annotated[
        str | None,
        Field(description="Short, descriptive name for the new dataset"),
    ] = None,
) -> Command:
    """Transform a dataset's geometry, producing a new dataset.

    Each op uses exactly one extra parameter — don't pass the others:
      "buffer"   — requires distance_meters (metres); grows each geometry by that distance
      "centroid" — no extra parameter; replaces each geometry with its centroid (Point)
      "simplify" — requires tolerance_meters (metres, e.g. 5); Douglas–Peucker simplification
      "dissolve" — optional `by` (attribute name): one feature per distinct value; omit `by` to
                   merge everything into a single feature

    Example — 100 m buffer around a set of points:
      {"dataset_id": "result_004", "op": "buffer", "distance_meters": 100, "alias": "rayon_100m"}

    On failure: dataset_not_found (bad dataset_id), bad_input (missing the parameter this op needs,
    an extra parameter that doesn't belong to this op, or a `by` attribute not in the dataset).
    """
    def _bad(message: str, suggestion: str) -> Command:
        return tool_error_command(
            ToolError(code="bad_input", message=message, suggestion=suggestion), tool_call_id
        )

    needed = _EXTRA_PARAM_BY_OP[op]
    supplied = {
        "distance_meters": distance_meters,
        "tolerance_meters": tolerance_meters,
        "by": by,
    }
    stray = [k for k, v in supplied.items() if v is not None and k != needed]
    if stray:
        return _bad(
            f"op='{op}' does not use {', '.join(stray)}",
            f"op='{op}' uses {needed or 'no extra parameter'}; drop {', '.join(stray)} and retry",
        )
    if needed == "distance_meters" and distance_meters is None:
        return _bad("op='buffer' requires distance_meters", "add distance_meters (metres)")
    if needed == "tolerance_meters" and tolerance_meters is None:
        return _bad("op='simplify' requires tolerance_meters", "add tolerance_meters (metres)")

    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    tolerance_deg = tolerance_meters / _METRES_PER_DEGREE if tolerance_meters is not None else None
    try:
        out = do_transform(gj, op, distance_meters=distance_meters, tolerance=tolerance_deg, by=by)
    except ValueError as e:
        return _bad(str(e), "fix the parameter the message points to and retry")

    params = {
        k: v
        for k, v in {
            "op": op,
            "distance_meters": distance_meters,
            "tolerance_meters": tolerance_meters,
            "by": by,
        }.items()
        if v is not None
    }
    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {
                "type": "derived",
                "filter_summary": f"{op}({dataset_id})",
            },
            "lineage": {
                "parent_ids": [dataset_id],
                "operation": "transform_geometry",
                "params": params,
            },
        },
    )
    meta = services.store.get_meta(rid)
    return dataset_created_command(
        _meta_lite(meta),
        tool_result={
            "dataset_id": rid,
            "alias": meta.alias,
            "feature_count": meta.feature_count,
            "bbox": list(meta.bbox),
        },
        state=state,
        tool_call_id=tool_call_id,
    )
