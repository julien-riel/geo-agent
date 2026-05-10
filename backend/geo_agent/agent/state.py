from typing import Annotated, Any

from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from typing_extensions import TypedDict

ERROR_HISTORY_CAP = 10


def append_errors(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append new errors to the history, capped at ERROR_HISTORY_CAP entries (newest last)."""
    merged = [*(left or []), *(right or [])]
    return merged[-ERROR_HISTORY_CAP:]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: RemainingSteps
    datasets: list[dict[str, Any]]      # serialized DatasetMetaLite
    active_layers: list[str]
    errors: Annotated[list[dict[str, Any]], append_errors]


def build_initial_state() -> AgentState:
    # remaining_steps is filled by the agent runtime; tests/initial input may omit it.
    return {
        "messages": [],
        "datasets": [],
        "active_layers": [],
        "errors": [],
    }  # type: ignore[typeddict-item]
