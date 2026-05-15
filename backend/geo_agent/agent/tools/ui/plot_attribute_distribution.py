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
from geo_agent.services.chart_data import top_values_for_chart


@tool
async def plot_attribute_distribution(
    dataset_id: str,
    attribute: str,
    chart_type: Literal["bar", "pie"],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> dict | Command:
    """Render a bar or pie chart of an attribute's value frequencies.

    Use for "show me the distribution of X", "what's the breakdown by type", or any
    "fréquence / répartition / camembert" question. The widget is drawn for the user.
    For numerical attributes prefer describe_dataset (min/max) or plot_aggregation.

    Example — bar of types:
      {"dataset_id": "result_003", "attribute": "type", "chart_type": "bar"}

    Example — pie of categories:
      {"dataset_id": "result_003", "attribute": "categorie", "chart_type": "pie"}

    Errors: dataset_not_found, bad_input (attribute not in dataset's schema).
    """
    services = get_services()
    try:
        meta = services.store.get_meta(dataset_id)
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    try:
        cd = top_values_for_chart(
            gj,
            attribute=attribute,
            chart_type=chart_type,
            dataset_id=meta.id,
            dataset_alias=meta.alias,
        )
    except KeyError:
        available = ", ".join(meta.attribute_schema.keys()) or "(none)"
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"attribute '{attribute}' not found in dataset {meta.id}",
                suggestion=f"available attributes: {available}",
            ),
            tool_call_id,
        )

    return cd.model_dump(mode="json")
