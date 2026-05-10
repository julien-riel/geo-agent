import pytest

from geo_agent.agent.graph import build_agent
from geo_agent.agent.registry import init_services
from geo_agent.config import Settings


@pytest.mark.live
async def test_agent_lists_layers_against_real_wfs(tmp_path) -> None:
    settings = Settings(DATA_DIR=tmp_path)
    init_services(settings)
    agent = build_agent(settings)

    response = await agent.ainvoke(
        {
            "messages": [{"role": "user", "content": "Quelles couches WFS sont disponibles ? Donne-moi les 3 premières."}],
            "datasets": [], "current_drawing": None, "active_layers": [], "last_error": None,
        },
        config={"configurable": {"thread_id": "test"}},
    )
    text = " ".join(m.content for m in response["messages"] if hasattr(m, "content"))
    assert "montreal" in text.lower() or "chaussees" in text.lower()
