import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import dataset_not_found_command
from geo_agent.agent.registry import get_services
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool


@tool
async def delete_dataset(
    id_or_alias: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delete a dataset (by id or alias) from the local store.

    Removes the dataset's geometry and metadata files, drops it from the visible map layers,
    and updates the session's dataset list. Downstream datasets that referenced it through
    lineage are NOT cascaded — they remain with a now-dangling parent id.
    """
    services = get_services()
    try:
        rid = services.store._resolve_id(id_or_alias)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, id_or_alias, tool_call_id)

    services.store.delete(rid)

    new_datasets = [d for d in (state.get("datasets") or []) if d.get("id") != rid]
    new_active = [x for x in (state.get("active_layers") or []) if x != rid]

    return Command(
        update={
            "datasets": new_datasets,
            "active_layers": new_active,
            "messages": [
                ToolMessage(content=json.dumps({"deleted": rid}), tool_call_id=tool_call_id),
            ],
        }
    )
