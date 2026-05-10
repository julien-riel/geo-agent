"""Helpers for tools to surface structured errors.

Tools can either:
- return a dict (success path)
- return a Command produced by `tool_error_command(...)` (error path) which both
  feeds the structured error to the LLM via a ToolMessage and appends it to
  AgentState.errors so the frontend can render it.
"""
import json

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from geo_agent.models import ToolError


def tool_error_command(error: ToolError, tool_call_id: str) -> Command:
    err = error.model_dump()
    return Command(
        update={
            "errors": [err],
            "messages": [
                ToolMessage(
                    content=json.dumps({"error": err}),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
