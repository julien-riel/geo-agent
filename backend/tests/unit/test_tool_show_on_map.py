from langgraph.types import Command

from geo_agent.agent.tools.show_on_map import show_on_map, hide_on_map

# InjectedToolCallId requires a full ToolCall dict with a tool_call_id field.
_TOOL_CALL_SHOW = {
    "args": {"dataset_id": "result_001"},
    "name": "show_on_map",
    "type": "tool_call",
    "id": "call_abc123",
}

_TOOL_CALL_HIDE = {
    "args": {"dataset_id": "result_001"},
    "name": "hide_on_map",
    "type": "tool_call",
    "id": "call_def456",
}


async def test_show_on_map_returns_command_updating_active_layers() -> None:
    result = await show_on_map.ainvoke(_TOOL_CALL_SHOW)
    assert isinstance(result, Command)
    update = result.update
    assert "active_layers" in update
    # The actual value is a reducer hint; we just check the call was made


async def test_hide_on_map_returns_command() -> None:
    result = await hide_on_map.ainvoke(_TOOL_CALL_HIDE)
    assert isinstance(result, Command)
