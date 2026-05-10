from typing import Annotated

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError
from geo_agent.services.spatial_ops import AttributePredicate, filter_by_attribute


@tool
async def filter_attributes(
    dataset_id: str,
    predicate: dict,
    tool_call_id: Annotated[str, InjectedToolCallId],
    alias: str | None = None,
) -> dict | Command:
    """Filter a dataset by an attribute predicate, producing a new dataset.

    predicate is {"property": str, "op": "eq"|"neq"|"lt"|"gt"|"lte"|"gte"|"in", "value": <any>}.
    The new dataset has parent_ids=[<source_dataset_id>] in its lineage.
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        known = [m.id for m in services.store.list()]
        return tool_error_command(
            ToolError(
                code="dataset_not_found",
                message=f"No dataset {dataset_id}",
                suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
            ),
            tool_call_id,
        )

    try:
        pred = AttributePredicate.model_validate(predicate)
    except Exception as e:
        return tool_error_command(
            ToolError(code="bad_input", message=f"Bad predicate: {e}"),
            tool_call_id,
        )

    out = filter_by_attribute(gj, pred)
    new_id = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{pred.property} {pred.op} {pred.value}"},
            "lineage": {
                "parent_ids": [dataset_id],
                "operation": "filter_attributes",
                "params": predicate,
            },
        },
    )
    meta = services.store.get_meta(new_id)
    return {
        "dataset_id": new_id,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
    }
