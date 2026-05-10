from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

from geo_agent.agent.prompts import SYSTEM_PROMPT


def format_datasets_summary(datasets: list[dict[str, Any]]) -> str:
    """Render a compact bullet list of datasets for inclusion in the system prompt."""
    if not datasets:
        return "Current datasets in this session: (none)"

    lines = ["Current datasets in this session:"]
    for d in datasets:
        bbox = d.get("bbox")
        bbox_str = f"[{', '.join(str(x) for x in bbox)}]" if bbox else "[]"
        lines.append(
            f"- {d.get('id')} (alias={d.get('alias')}, "
            f"operation={d.get('operation')}, "
            f"{d.get('feature_count')} features, "
            f"bbox={bbox_str})"
        )
    return "\n".join(lines)


def build_prompt(state: dict) -> list[BaseMessage]:
    """LangGraph `prompt=` callable: prepend a SystemMessage with the dataset summary."""
    summary = format_datasets_summary(state.get("datasets") or [])
    sys_text = f"{SYSTEM_PROMPT}\n---\n{summary}"
    messages = state.get("messages") or []
    return [SystemMessage(content=sys_text), *messages]
