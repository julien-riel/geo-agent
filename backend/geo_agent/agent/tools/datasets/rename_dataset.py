import json
import re
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import dataset_not_found_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError

_ALIAS_RE = re.compile(r"^\S{1,64}$")


@tool
async def rename_dataset(
    id_or_alias: str,
    new_alias: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Set or change a dataset's short human-readable alias.

    The alias must be non-empty, contain no whitespace, and be at most 64 characters.
    Aliases must be unique across the session.
    """
    services = get_services()

    if not _ALIAS_RE.match(new_alias or ""):
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"Invalid alias {new_alias!r}",
                suggestion=(
                    "alias must be non-empty, contain no whitespace, "
                    "and be at most 64 characters"
                ),
            ),
            tool_call_id,
        )

    try:
        rid = services.store._resolve_id(id_or_alias)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, id_or_alias, tool_call_id)

    for m in services.store.list():
        if m.id != rid and m.alias == new_alias:
            return tool_error_command(
                ToolError(
                    code="alias_conflict",
                    message=f"Alias {new_alias!r} already in use",
                    suggestion=f"alias '{new_alias}' is already used by {m.id}; pick another",
                ),
                tool_call_id,
            )

    services.store.update_alias(rid, new_alias)

    new_datasets = []
    for d in state.get("datasets") or []:
        if d.get("id") == rid:
            new_datasets.append({**d, "alias": new_alias})
        else:
            new_datasets.append(d)

    return Command(
        update={
            "datasets": new_datasets,
            "messages": [
                ToolMessage(
                    content=json.dumps({"id": rid, "alias": new_alias}),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
