from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI

from geo_agent.agent.graph import build_agent
from geo_agent.config import Settings


def mount_copilotkit(app: FastAPI, settings: Settings) -> None:
    """Expose the LangGraph agent as an AGUI-compatible SSE endpoint at /agents/geo-agent.

    The Next.js frontend connects via @copilotkit/runtime's LangGraphHttpAgent
    pointing to this URL. We use ag_ui_langgraph directly because the higher-level
    copilotkit.LangGraphAGUIAgent has a broken dict_repr in 0.1.88, and copilotkit's
    own FastAPI integration speaks the deprecated v1 remote-endpoint protocol that
    @copilotkit/runtime 1.57 no longer supports.
    """
    agent = LangGraphAgent(
        name="geo-agent",
        description="Spatial analysis agent for Montreal WFS data",
        graph=build_agent(settings),
    )
    add_langgraph_fastapi_endpoint(app, agent, path="/agents/geo-agent")
