from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from geo_agent.agent.prompts import SYSTEM_PROMPT
from geo_agent.agent.tools.aggregate import aggregate
from geo_agent.agent.tools.describe_dataset import describe_dataset
from geo_agent.agent.tools.filter_attributes import filter_attributes
from geo_agent.agent.tools.list_datasets import list_datasets
from geo_agent.agent.tools.list_wfs_layers import list_wfs_layers
from geo_agent.agent.tools.select_features import select_features
from geo_agent.agent.tools.show_on_map import hide_on_map, show_on_map
from geo_agent.config import Settings

TOOLS = [
    list_wfs_layers,
    select_features,
    aggregate,
    filter_attributes,
    describe_dataset,
    list_datasets,
    show_on_map,
    hide_on_map,
]


def build_agent(settings: Settings):
    llm = ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        temperature=0.3,
    )
    return create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)
