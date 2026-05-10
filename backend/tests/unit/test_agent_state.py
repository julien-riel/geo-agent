from datetime import datetime, timezone

from geo_agent.agent.state import AgentState, build_initial_state
from geo_agent.models import DatasetMetaLite


def test_initial_state_is_empty() -> None:
    s = build_initial_state()
    assert s["datasets"] == []
    assert s["current_drawing"] is None
    assert s["active_layers"] == []
    assert s["last_error"] is None


def test_state_typed_dict_accepts_dataset() -> None:
    s: AgentState = build_initial_state()
    s["datasets"].append(
        DatasetMetaLite(
            id="result_001", alias="x", feature_count=1, bbox=(0, 0, 1, 1), layer="parcs", operation="select"
        ).model_dump()
    )
    assert s["datasets"][0]["id"] == "result_001"
