from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from geo_agent.agent.prompt_builder import build_prompt
from geo_agent.agent.state import AgentState
from geo_agent.agent.tools import ALL_TOOLS
from geo_agent.config import Settings

TOOLS = ALL_TOOLS


def _build_llm(settings: Settings) -> BaseChatModel:
    if settings.LLM_PROVIDER == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is empty. "
                "Set it in .env or switch LLM_PROVIDER to 'ollama'."
            )
        return ChatOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MODEL,
            temperature=0,
            default_headers={
                "HTTP-Referer": settings.OPENROUTER_APP_URL,
                "X-Title": settings.OPENROUTER_APP_NAME,
            },
        )
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        temperature=0,
    )


def _bind_tools_serial(llm: BaseChatModel):
    """Bind the tools, disabling parallel tool-calling.

    Several tools mutate session state (`datasets`, `active_layers`) by returning
    the full new list on a non-reducer (LastValue) channel; two such tool calls in
    one graph step collide with `InvalidUpdateError`. Forcing one tool call per
    step avoids that — and lets the agent see each result before its next move.
    """
    try:
        return llm.bind_tools(TOOLS, parallel_tool_calls=False)
    except TypeError:
        # Some providers' bind_tools (e.g. Ollama) don't accept parallel_tool_calls.
        return llm.bind_tools(TOOLS)


def build_agent(settings: Settings):
    llm = _build_llm(settings)
    return create_react_agent(
        model=_bind_tools_serial(llm),
        tools=TOOLS,
        prompt=build_prompt,
        state_schema=AgentState,
        checkpointer=MemorySaver(),
    )
