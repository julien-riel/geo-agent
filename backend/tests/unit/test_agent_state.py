from geo_agent.agent.state import (
    AgentState,
    ERROR_HISTORY_CAP,
    append_errors,
    build_initial_state,
)
from geo_agent.models import DatasetMetaLite


def test_initial_state_has_empty_collections() -> None:
    s = build_initial_state()
    assert "current_drawing" not in s
    assert s["datasets"] == []
    assert s["active_layers"] == []
    assert s["errors"] == []
    assert s["messages"] == []


def test_state_typed_dict_accepts_dataset() -> None:
    s: AgentState = build_initial_state()
    s["datasets"].append(
        DatasetMetaLite(
            id="result_001", alias="x", feature_count=1, bbox=(0, 0, 1, 1), layer="parcs", operation="select"
        ).model_dump()
    )
    assert s["datasets"][0]["id"] == "result_001"


def test_append_errors_concatenates_lists() -> None:
    left = [{"code": "a", "message": "a"}]
    right = [{"code": "b", "message": "b"}]
    assert append_errors(left, right) == [
        {"code": "a", "message": "a"},
        {"code": "b", "message": "b"},
    ]


def test_append_errors_caps_history_keeping_newest() -> None:
    left = [{"code": f"old_{i}", "message": "x"} for i in range(ERROR_HISTORY_CAP)]
    right = [{"code": "new", "message": "x"}]
    out = append_errors(left, right)
    assert len(out) == ERROR_HISTORY_CAP
    assert out[-1] == {"code": "new", "message": "x"}
    assert out[0] == {"code": "old_1", "message": "x"}  # oldest dropped


def test_append_errors_handles_none_inputs() -> None:
    # LangGraph may invoke the reducer with empty/None on first update
    assert append_errors([], [{"code": "c", "message": "m"}]) == [{"code": "c", "message": "m"}]
    assert append_errors(None, [{"code": "c", "message": "m"}]) == [{"code": "c", "message": "m"}]  # type: ignore[arg-type]
    assert append_errors([{"code": "c", "message": "m"}], None) == [{"code": "c", "message": "m"}]  # type: ignore[arg-type]
