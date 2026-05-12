from geo_agent.agent.state import (
    ERROR_HISTORY_CAP,
    AgentState,
    append_errors,
    build_initial_state,
    merge_active_layers,
    merge_datasets,
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


def _ds(i: str, alias: str = "") -> dict:
    return {"id": i, "alias": alias or i}


def test_merge_datasets_full_replace_single_writer() -> None:
    # tools return the full desired list; with one write it must behave like LastValue
    assert merge_datasets([_ds("r1")], [_ds("r1"), _ds("r2")]) == [_ds("r1"), _ds("r2")]


def test_merge_datasets_subset_write_is_authoritative() -> None:
    # delete: write drops r2
    assert merge_datasets([_ds("r1"), _ds("r2")], [_ds("r1")]) == [_ds("r1")]
    # clear: write is empty
    assert merge_datasets([_ds("r1"), _ds("r2")], []) == []
    # rename: same ids, new alias wins
    assert merge_datasets([_ds("r1", "old")], [_ds("r1", "new")]) == [_ds("r1", "new")]


def test_merge_datasets_concurrent_creates_are_unioned() -> None:
    # two parallel select_features both started from [r1] and each added one
    step1 = merge_datasets([_ds("r1")], [_ds("r1"), _ds("r2")])
    out = merge_datasets(step1, [_ds("r1"), _ds("r3")])
    assert {d["id"] for d in out} == {"r1", "r2", "r3"}


def test_merge_datasets_handles_none_inputs() -> None:
    assert merge_datasets(None, [_ds("r1")]) == [_ds("r1")]  # type: ignore[arg-type]
    assert merge_datasets([_ds("r1")], None) == [_ds("r1")]  # type: ignore[arg-type]


def test_merge_active_layers() -> None:
    assert merge_active_layers(["a"], ["a", "b"]) == ["a", "b"]      # show b
    assert merge_active_layers(["a", "b"], ["a"]) == ["a"]            # hide b
    assert merge_active_layers(["a", "b"], []) == []                  # clear
    assert merge_active_layers(None, ["a"]) == ["a"]  # type: ignore[arg-type]
