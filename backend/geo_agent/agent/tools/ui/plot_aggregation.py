from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId
from langgraph.types import Command

from geo_agent.agent.error_helpers import (
    dataset_not_found_command,
    tool_error_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool
from geo_agent.models import ToolError
from geo_agent.services.chart_data import aggregation_for_chart


@tool
async def plot_aggregation(
    dataset_id: str,
    group_by: str,
    op: Literal["count", "sum", "mean", "min", "max"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    metric: str | None = None,
) -> dict | Command:
    """Render a grouped bar chart of <op> partitioned by <group_by>.

    Use for "total length by type", "count by borough", "average area per category",
    or any "compare / total par / moyenne par" question. The widget is drawn for the user.

    op="count" ignores metric. Other ops (sum/mean/min/max) require a metric attribute.

    Example — count by type:
      {"dataset_id": "result_003", "group_by": "type", "op": "count"}

    Example — sum of length by type:
      {"dataset_id": "result_003", "group_by": "type", "op": "sum", "metric": "longueur"}

    Errors: dataset_not_found, bad_input (missing metric, unknown group_by).
    """
    if op != "count" and metric is None:
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"op '{op}' requires a metric attribute",
                suggestion="pass metric=<attribute name>",
            ),
            tool_call_id,
        )

    services = get_services()
    try:
        meta = services.store.get_meta(dataset_id)
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    if group_by not in meta.attribute_schema:
        available = ", ".join(meta.attribute_schema.keys()) or "(none)"
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"group_by '{group_by}' not in schema of {meta.id}",
                suggestion=f"available attributes: {available}",
            ),
            tool_call_id,
        )

    if metric is not None and metric not in meta.attribute_schema:
        available = ", ".join(meta.attribute_schema.keys()) or "(none)"
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"metric '{metric}' not in schema of {meta.id}",
                suggestion=f"available attributes: {available}",
            ),
            tool_call_id,
        )

    cd = aggregation_for_chart(
        gj,
        group_by=group_by,
        metric=metric,
        op=op,
        dataset_id=meta.id,
        dataset_alias=meta.alias,
    )
    return cd.model_dump(mode="json")
