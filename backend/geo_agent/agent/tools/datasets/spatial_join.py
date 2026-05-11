from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import (
    dataset_created_command,
    dataset_not_found_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite
from geo_agent.services.geometry_ops import spatial_join as do_spatial_join


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
async def spatial_join(
    left_id: str,
    right_id: str,
    predicate: Literal["intersects", "within", "contains"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[
        str | None,
        Field(description="Short, descriptive name for the new dataset"),
    ] = None,
) -> Command:
    """Attach `right`'s attributes to each feature of `left` based on a spatial relation.

    Produces a new dataset with `left`'s geometry. Every `left` feature is kept; when no `right`
    feature satisfies `predicate`, the joined attributes are null. All `right` attribute names get
    a `_r` suffix to avoid collisions. When a `left` feature matches several `right` features, the
    first match wins.

    predicate: "intersects" | "within" | "contains"

    Example — tag each street with the borough it falls in:
      {"left_id": "result_003", "right_id": "result_002", "predicate": "within",
       "alias": "rues_avec_arrondissement"}

    On failure: dataset_not_found (bad left_id/right_id).
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

    out = do_spatial_join(left_gj, right_gj, predicate)
    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {
                "type": "derived",
                "filter_summary": f"sjoin({left_id}, {right_id}, {predicate})",
            },
            "lineage": {
                "parent_ids": [left_id, right_id],
                "operation": "spatial_join",
                "params": {"predicate": predicate},
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
