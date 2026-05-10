from typing import Any, TypedDict


class AgentState(TypedDict):
    datasets: list[dict[str, Any]]      # serialized DatasetMetaLite
    current_drawing: dict[str, Any] | None  # GeoJSON Polygon (or null)
    active_layers: list[str]
    last_error: str | None


def build_initial_state() -> AgentState:
    return {
        "datasets": [],
        "current_drawing": None,
        "active_layers": [],
        "last_error": None,
    }
