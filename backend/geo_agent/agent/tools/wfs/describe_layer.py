from typing import Annotated

import httpx
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError


@tool
async def describe_wfs_layer(
    layer: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> dict | Command:
    """Return the attribute schema and geometry property of a WFS layer.

    Call this before `select_features` with an `attribute_filter` when you don't know
    the layer's attribute names. No features are returned.

    Output: {"layer", "geometry_property", "attributes": {name: type}} where `type` is
    one of "string" | "number" | "boolean".

    Example:
      {"layer": "montreal:chaussees"}

    On failure: layer_not_found (the WFS server could not describe that layer).
    """
    services = get_services()
    try:
        schema = await services.wfs.describe_feature_type(layer)
    except httpx.HTTPStatusError:
        return tool_error_command(
            ToolError(
                code="layer_not_found",
                message=f"WFS layer {layer!r} not found or not describable",
                suggestion="call list_wfs_layers to see valid layer names",
            ),
            tool_call_id,
        )
    return {
        "layer": layer,
        "geometry_property": schema.geom_property,
        "attributes": schema.attribute_schema,
    }
