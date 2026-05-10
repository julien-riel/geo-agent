from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "results").mkdir()
    (tmp_path / "sessions").mkdir()
    return tmp_path


def make_tool_call(name: str, args: dict[str, Any], call_id: str = "test-call") -> dict[str, Any]:
    """Wrap tool args as a full ToolCall — required when the tool uses InjectedToolCallId."""
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}
