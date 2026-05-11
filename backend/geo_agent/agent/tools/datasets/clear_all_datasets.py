import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.registry import get_services


@tool
async def clear_all_datasets(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delete every dataset in the current session — destructive and irreversible.

    Only call this when the user explicitly asks to start over (e.g. "efface tous les datasets",
    "repars de zéro"). Do not call it on your own initiative.
    """
    services = get_services()
    count = 0
    for m in services.store.list():
        services.store.delete(m.id)
        count += 1

    return Command(
        update={
            "datasets": [],
            "active_layers": [],
            "messages": [
                ToolMessage(content=json.dumps({"deleted": count}), tool_call_id=tool_call_id),
            ],
        }
    )
