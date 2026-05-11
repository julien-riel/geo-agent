from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError


def _known_dataset_ids() -> list[str]:
    return [m.id for m in get_services().store.list()]


def _dataset_exists(dataset_id: str) -> bool:
    return dataset_id in _known_dataset_ids()


@tool
async def show_on_map(
    dataset_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Add a dataset to the visible layers on the map.

    Call this after creating or referencing a dataset the user should see.
    """
    if not _dataset_exists(dataset_id):
        known = _known_dataset_ids()
        return tool_error_command(
            ToolError(
                code="dataset_not_found",
                message=f"Cannot show {dataset_id}: no such dataset",
                suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
            ),
            tool_call_id,
        )

    current = list(state.get("active_layers") or [])
    if dataset_id not in current:
        current.append(dataset_id)

    return Command(
        update={
            "active_layers": current,
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
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Hide a dataset from the map (does not delete the data)."""
    current = [x for x in (state.get("active_layers") or []) if x != dataset_id]
    return Command(
        update={
            "active_layers": current,
            "messages": [
                ToolMessage(
                    content=f"Dataset {dataset_id} hidden from the map.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
