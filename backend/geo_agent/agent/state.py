from typing import Any, TypedDict


class AgentState(TypedDict):
    datasets: list[dict[str, Any]]      # serialized DatasetMetaLite
    active_layers: list[str]
    last_error: str | None


def build_initial_state() -> AgentState:
    return {
        "datasets": [],
        "active_layers": [],
        "last_error": None,
    }
