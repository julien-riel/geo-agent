from typing import Any


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
