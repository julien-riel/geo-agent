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
from geo_agent.services.geometry_ops import overlay as do_overlay


def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
        parent_ids=meta.lineage.parent_ids,
    )


@tool
async def spatial_overlay(
    left_id: str,
    right_id: str,
    op: Literal["intersection", "union", "difference", "clip"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[
        str | None, Field(description="Short, descriptive name for the new dataset")
    ] = None,
) -> Command:
    """Combine two datasets geometrically, producing a new dataset.

    op:
      "intersection" / "clip" — keep only the parts of `left` that fall inside `right`
                                (keeps left's attributes; non-overlapping features are dropped)
      "union"                 — geometric union of both layers' features (attributes from both)
      "difference"            — `left` minus the parts overlapping `right` (keeps left's attributes)

    Example — streets clipped to a zone:
      {"left_id": "result_003", "right_id": "result_001", "op": "intersection",
       "alias": "rues_dans_zone"}

    On failure: dataset_not_found (bad left_id/right_id),
    empty_result (left and right do not overlap).
    """
    services = get_services()
    try:
        left_gj = services.store.get_geojson(left_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, left_id, tool_call_id)
    try:
        right_gj = services.store.get_geojson(right_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, right_id, tool_call_id)

    out = do_overlay(left_gj, right_gj, op)
    if not out.get("features"):
        return tool_error_command(
            ToolError(
                code="empty_result",
                message=f"{op}({left_id}, {right_id}) produced no features",
                suggestion="left and right may not overlap; check the inputs or try a different op",
            ),
            tool_call_id,
        )

    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{op}({left_id}, {right_id})"},
            "lineage": {
                "parent_ids": [left_id, right_id],
                "operation": "spatial_overlay",
                "params": {"op": op},
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
