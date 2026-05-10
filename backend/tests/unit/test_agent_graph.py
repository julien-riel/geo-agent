from pathlib import Path

import pytest

from geo_agent.agent.graph import build_agent
from geo_agent.agent.registry import init_services
from geo_agent.config import Settings


def test_build_agent_returns_runnable(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    settings = Settings()
    init_services(settings)
    agent = build_agent(settings)
    assert agent is not None
    # Has the canonical LangGraph compiled-graph interface
    assert hasattr(agent, "ainvoke")
