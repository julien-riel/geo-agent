from copilotkit import CopilotKitRemoteEndpoint, LangGraphAGUIAgent
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from fastapi import FastAPI

from geo_agent.agent.graph import build_agent
from geo_agent.config import Settings


def mount_copilotkit(app: FastAPI, settings: Settings) -> None:
    agent = LangGraphAGUIAgent(
        name="geo-agent",
        description="Spatial analysis agent for Montreal WFS data",
        graph=build_agent(settings),
    )
    sdk = CopilotKitRemoteEndpoint(agents=[agent])
    add_fastapi_endpoint(app, sdk, "/copilotkit")
