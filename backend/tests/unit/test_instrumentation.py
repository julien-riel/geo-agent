from typing import Annotated

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId
from langgraph.types import Command

from geo_agent.agent.tools._instrumentation import (
    _build_event,
    _peek_dataset_result,
    _summarize_args,
    _summarize_filter_attributes,
    _summarize_select_features,
    instrumented_tool,
)


@instrumented_tool
def _echo(value: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Test tool: return a Command echoing the value."""
    return Command(
        update={
            "messages": [ToolMessage(content=f"echo:{value}", tool_call_id=tool_call_id)],
        }
    )


@instrumented_tool
def _scalar(value: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> str:
    """Test tool: return a scalar (LangChain auto-wraps it)."""
    return f"scalar:{value}"


@instrumented_tool
def _raiser(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Test tool: raise to verify error event + reraise."""
    raise RuntimeError("kaboom")


@instrumented_tool
def _tool_errored(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Test tool: return a Command with a structured error (mimics tool_error_command)."""
    return Command(
        update={
            "errors": [{"code": "bad_input", "message": "nope"}],
            "messages": [ToolMessage(content='{"error":"nope"}', tool_call_id=tool_call_id)],
        }
    )


@instrumented_tool
async def _async_echo(value: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Async test tool: return a Command echoing the value via the ainvoke path."""
    return Command(
        update={
            "messages": [
                ToolMessage(content=f"async:{value}", tool_call_id=tool_call_id)
            ],
        }
    )


def test_event_payload_shape() -> None:
    ev = _build_event(
        event_id="te_x",
        tool_call_id="tc_1",
        tool="select_features",
        args_raw={"layer": "chaussees"},
        status="running",
        started_at=1.0,
    )
    assert ev["id"] == "te_x"
    assert ev["tool"] == "select_features"
    assert ev["status"] == "running"
    assert ev["started_at"] == 1.0
    assert ev["ended_at"] is None
    assert ev["duration_ms"] is None
    assert "args_summary" in ev
    assert "args_raw" in ev


def test_summarize_args_redacts_injected() -> None:
    out = _summarize_args({"layer": "x", "tool_call_id": "tc_1", "state": {}})
    assert "tool_call_id" not in out
    assert "state" not in out
    assert out["layer"] == "x"


def test_command_returning_tool_gets_tool_events_appended() -> None:
    result = _echo.invoke(
        {"name": "_echo", "args": {"value": "hi"}, "id": "tc_1", "type": "tool_call"}
    )
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert len(events) == 1
    final = events[0]
    assert final["status"] == "ok"
    assert final["tool"] == "_echo"
    assert final["tool_call_id"] == "tc_1"
    assert final["duration_ms"] is not None
    # The original update["messages"] is preserved
    assert any(isinstance(m, ToolMessage) for m in result.update["messages"])


def test_scalar_returning_tool_gets_wrapped_in_command() -> None:
    result = _scalar.invoke(
        {"name": "_scalar", "args": {"value": "hi"}, "id": "tc_2", "type": "tool_call"}
    )
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert events[0]["status"] == "ok"
    # ToolMessage was synthesised with the scalar content
    msgs = result.update["messages"]
    assert msgs and isinstance(msgs[0], ToolMessage)
    assert msgs[0].content == "scalar:hi"


def test_exception_writes_error_event_and_reraises() -> None:
    with pytest.raises(RuntimeError, match="kaboom"):
        _raiser.invoke({"name": "_raiser", "args": {}, "id": "tc_3", "type": "tool_call"})


def test_tool_error_command_results_in_error_event_not_ok() -> None:
    result = _tool_errored.invoke(
        {"name": "_tool_errored", "args": {}, "id": "tc_4", "type": "tool_call"}
    )
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"]["code"] == "bad_input"
    # Pre-existing errors stay intact (the decorator amends tool_events without touching errors)
    assert result.update["errors"][0]["code"] == "bad_input"


async def test_async_command_returning_tool() -> None:
    result = await _async_echo.ainvoke(
        {"name": "_async_echo", "args": {"value": "hi"}, "id": "tc_a", "type": "tool_call"}
    )
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert events[0]["tool_call_id"] == "tc_a"


def test_peek_dataset_result_extracts_id_and_count() -> None:
    cmd = Command(
        update={
            "messages": [
                ToolMessage(
                    content='{"dataset_id": "ds_42", "feature_count": 7}',
                    tool_call_id="x",
                )
            ]
        }
    )
    assert _peek_dataset_result(cmd) == "7 features → ds_42"


def test_peek_dataset_result_handles_no_dataset_payload() -> None:
    cmd = Command(
        update={
            "messages": [ToolMessage(content='{"foo": "bar"}', tool_call_id="x")]
        }
    )
    out = _peek_dataset_result(cmd)
    assert "foo" in out  # falls through to repr of the parsed payload


def test_summarize_select_features_formats_layer_and_predicate() -> None:
    args = {"layer": "chaussees", "spatial_predicate": "intersects", "alias": "roads"}
    summary, _ = _summarize_select_features(args, "irrelevant")
    assert summary == "layer=chaussees, predicate=intersects, alias=roads"


def test_summarize_select_features_whole_layer() -> None:
    args = {"layer": "chaussees"}  # no spatial_predicate
    summary, _ = _summarize_select_features(args, "irrelevant")
    assert "whole-layer" in summary


def test_summarize_filter_attributes_unpacks_predicate_dict() -> None:
    args = {
        "dataset_id": "ds_3",
        "predicate": {"property": "length", "op": "gt", "value": 200},
    }
    cmd = Command(
        update={
            "messages": [
                ToolMessage(
                    content='{"dataset_id": "ds_4", "feature_count": 12}',
                    tool_call_id="x",
                )
            ]
        }
    )
    summary, result_summary = _summarize_filter_attributes(args, cmd)
    assert "ds_3" in summary and "length" in summary and "gt" in summary
    assert "12 features" in result_summary
