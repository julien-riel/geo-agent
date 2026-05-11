from types import SimpleNamespace

from geo_agent.agent.error_helpers import dataset_not_found_command


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
