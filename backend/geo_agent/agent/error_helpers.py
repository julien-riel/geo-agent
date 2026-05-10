"""Helpers for tools to surface structured errors and dataset additions.

Tools can either:
- return a dict (success path) — auto-wrapped in a ToolMessage by LangChain
- return a Command produced by `tool_error_command(...)` (error path) which both
  feeds the structured error to the LLM via a ToolMessage and appends it to
  AgentState.errors so the frontend can render it
- return a Command produced by `dataset_created_command(...)` to register a
  newly produced dataset in AgentState.datasets so the frontend renders it
  automatically without a separate REST round-trip.
"""
import json
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from geo_agent.models import DatasetMetaLite, ToolError


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


def dataset_created_command(
    meta: DatasetMetaLite,
    tool_result: dict[str, Any],
    state: dict[str, Any],
    tool_call_id: str,
) -> Command:
    """Register a newly produced dataset in state.datasets and feed result back to the LLM."""
    current = list(state.get("datasets") or [])
    if not any(d.get("id") == meta.id for d in current):
        current.append(meta.model_dump(mode="json"))
    return Command(
        update={
            "datasets": current,
            "messages": [
                ToolMessage(
                    content=json.dumps(tool_result),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
