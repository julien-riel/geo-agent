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
        Field(description="Required for op='buffer'; in metres"),
    ] = None,
    tolerance: Annotated[
        float | None,
        Field(description="Required for op='simplify'; in degrees, e.g. 0.0001"),
    ] = None,
    by: Annotated[
        str | None,
        Field(
            description=(
                "For op='dissolve': attribute to merge by; omit to merge everything"
            )
        ),
    ] = None,
    alias: Annotated[
        str | None,
        Field(description="Short, descriptive name for the new dataset"),
    ] = None,
) -> Command:
    """Transform a dataset's geometry, producing a new dataset.

    op:
      "buffer"   — requires distance_meters (metres); grows each geometry by that distance
      "centroid" — replaces each geometry with its centroid (Point)
      "simplify" — requires tolerance (degrees, e.g. 0.0001); Douglas–Peucker simplification
      "dissolve" — merge features; with `by` (attribute name), one feature per distinct value

    Example — 100 m buffer around a set of points:
      {"dataset_id": "result_004", "op": "buffer", "distance_meters": 100, "alias": "rayon_100m"}

    On failure: dataset_not_found (bad dataset_id), bad_input (missing distance_meters/tolerance,
    or a `by` attribute that is not in the dataset).
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    try:
        out = do_transform(
            gj, op, distance_meters=distance_meters, tolerance=tolerance, by=by
        )
    except ValueError as e:
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=str(e),
                suggestion="provide the missing parameter and retry",
            ),
            tool_call_id,
        )

    params = {
        k: v
        for k, v in {
            "op": op,
            "distance_meters": distance_meters,
            "tolerance": tolerance,
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
