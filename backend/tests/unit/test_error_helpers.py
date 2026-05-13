from types import SimpleNamespace

from geo_agent.agent.error_helpers import dataset_created_command, dataset_not_found_command
from geo_agent.models import DatasetMetaLite


class _FakeStore:
    def list(self):
        return [SimpleNamespace(id="result_001"), SimpleNamespace(id="result_002")]


class _EmptyStore:
    def list(self):
        return []


def test_dataset_not_found_command_lists_known_ids() -> None:
    cmd = dataset_not_found_command(_FakeStore(), "result_999", "t")
    err = cmd.update["errors"][0]
    assert err["code"] == "dataset_not_found"
    assert "result_001" in err["suggestion"] and "result_002" in err["suggestion"]
    assert cmd.update["messages"][0].tool_call_id == "t"


def test_dataset_not_found_command_handles_empty_store() -> None:
    cmd = dataset_not_found_command(_EmptyStore(), "result_999", "t")
    assert cmd.update["errors"][0]["suggestion"] == "Available IDs: (none)"


def test_dataset_created_command_writes_tool_call_id_on_dataset() -> None:
    meta = DatasetMetaLite(
        id="result_007",
        alias="parcs",
        feature_count=12,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer="parcs",
        operation="select_features",
        parent_ids=[],
    )
    cmd = dataset_created_command(
        meta,
        tool_result={"dataset_id": "result_007"},
        state={"datasets": []},
        tool_call_id="tc-abc123",
    )
    ds = cmd.update["datasets"][0]
    assert ds["tool_call_id"] == "tc-abc123"
    assert ds["id"] == "result_007"
