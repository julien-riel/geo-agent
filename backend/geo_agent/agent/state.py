from typing import Annotated, Any

from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from typing_extensions import TypedDict

ERROR_HISTORY_CAP = 10
INSPECTION_HISTORY_CAP = 5


def append_errors(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append new errors to the history, capped at ERROR_HISTORY_CAP entries (newest last)."""
    merged = [*(left or []), *(right or [])]
    return merged[-ERROR_HISTORY_CAP:]


def append_inspections(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append new inspect_dataset payloads, capped at INSPECTION_HISTORY_CAP (newest last)."""
    merged = [*(left or []), *(right or [])]
    return merged[-INSPECTION_HISTORY_CAP:]


def merge_datasets(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Reducer for the `datasets` channel.

    Tools normally return the full desired list (so a single write per step behaves
    like LastValue). If two tool calls land in the same step (parallel tool-calling
    — which we also disable at the model level), this merges them instead of
    raising InvalidUpdateError: a write whose ids are a subset of the current state
    is treated as authoritative (delete / clear / rename), otherwise the writes are
    unioned by `id` with the newer entry winning.
    """
    left = left or []
    if right is None:  # defensive: a non-write — keep current
        return left
    left_ids = {d.get("id") for d in left}
    if {d.get("id") for d in right} <= left_ids:
        return right
    by_id = {d.get("id"): d for d in left}
    for d in right:
        by_id[d.get("id")] = d
    return list(by_id.values())


def merge_active_layers(left: list[str], right: list[str]) -> list[str]:
    """Reducer for `active_layers`: subset write wins (hide/clear), else union (show)."""
    left = left or []
    if right is None:
        return left
    if set(right) <= set(left):
        return right
    seen: dict[str, None] = {}
    for x in (*left, *right):
        seen.setdefault(x, None)
    return list(seen)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: RemainingSteps
    datasets: Annotated[list[dict[str, Any]], merge_datasets]  # serialized DatasetMetaLite
    active_layers: Annotated[list[str], merge_active_layers]
    errors: Annotated[list[dict[str, Any]], append_errors]
    # Full inspect_dataset payloads, for the frontend widget only — the model gets back just a
    # short confirmation, so a 50-row feature table never lands in its context.
    inspections: Annotated[list[dict[str, Any]], append_inspections]


def build_initial_state() -> AgentState:
    # remaining_steps is filled by the agent runtime; tests/initial input may omit it.
    return {
        "messages": [],
        "datasets": [],
        "active_layers": [],
        "errors": [],
        "inspections": [],
    }  # type: ignore[typeddict-item]
