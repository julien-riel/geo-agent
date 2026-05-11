from typing import Annotated

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError


@tool
async def describe_dataset(
    id_or_alias: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> dict | Command:
    """Return full metadata for a dataset by id (e.g. 'result_001') or alias.

    Use this to refresh your memory about a dataset's bbox, attribute schema, or lineage
    without reading the geometry. The geometry is never returned.
    """
    services = get_services()
    metas = services.store.list()
    for m in metas:
        if m.id == id_or_alias or m.alias == id_or_alias:
            return m.model_dump(mode="json")

    known = [f"{m.id} (alias={m.alias})" for m in metas]
    return tool_error_command(
        ToolError(
            code="dataset_not_found",
            message=f"No dataset {id_or_alias}",
            suggestion=f"Available: {', '.join(known) if known else '(none)'}",
        ),
        tool_call_id,
    )
