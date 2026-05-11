from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError
from geo_agent.services.spatial_ops import aggregate as do_aggregate


@tool
async def aggregate(
    dataset_id: str,
    op: Literal["count", "sum", "mean", "min", "max"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    attribute: str | None = None,
    group_by: str | None = None,
) -> dict | Command:
    """Compute a statistic over a dataset's features.

    op="count" ignores attribute; other ops require an attribute name.
    Use group_by to partition results by an attribute (e.g., op="count", group_by="type").
    Result: {"value": <number or null>, "groups": [{"key", "value"}]} when group_by is set.
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        known = [m.id for m in services.store.list()]
        return tool_error_command(
            ToolError(
                code="dataset_not_found",
                message=f"No dataset named {dataset_id}",
                suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
            ),
            tool_call_id,
        )

    try:
        return do_aggregate(gj, op=op, attribute=attribute, group_by=group_by)
    except ValueError as e:
        return tool_error_command(
            ToolError(code="bad_input", message=str(e)),
            tool_call_id,
        )
