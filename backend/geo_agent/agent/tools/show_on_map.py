from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command


@tool
async def show_on_map(
    dataset_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Add a dataset to the visible layers on the map.

    Call this after creating or referencing a dataset the user should see.
    """
    return Command(
        update={
            "active_layers": [dataset_id],  # merged via reducer in agent state
            "messages": [
                ToolMessage(
                    content=f"Dataset {dataset_id} is now visible on the map.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
async def hide_on_map(
    dataset_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Hide a dataset from the map (does not delete the data)."""
    return Command(
        update={
            "active_layers_remove": [dataset_id],  # handled by reducer
            "messages": [
                ToolMessage(
                    content=f"Dataset {dataset_id} hidden from the map.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
