from typing import Literal

from langchain_core.tools import tool

from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError
from geo_agent.services.spatial_ops import aggregate as do_aggregate


@tool
async def aggregate(
    dataset_id: str,
    op: Literal["count", "sum", "mean", "min", "max"],
    attribute: str | None = None,
    group_by: str | None = None,
) -> dict:
    """Compute a statistic over a dataset's features.

    op="count" ignores attribute; other ops require an attribute name.
    Use group_by to partition results by an attribute (e.g., op="count", group_by="type").
    Result: {"value": <number or null>, "groups": [{"key", "value"}]} when group_by is set.
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return {"error": ToolError(code="dataset_not_found", message=f"No dataset named {dataset_id}").model_dump()}

    try:
        return do_aggregate(gj, op=op, attribute=attribute, group_by=group_by)
    except ValueError as e:
        return {"error": ToolError(code="bad_input", message=str(e)).model_dump()}
