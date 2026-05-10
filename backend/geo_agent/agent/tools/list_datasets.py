from langchain_core.tools import tool

from geo_agent.agent.registry import get_services


@tool
async def list_datasets() -> list[dict]:
    """List all datasets currently available in this session (id, alias, layer, count, bbox).

    Returns lightweight metadata only — no geometries.
    """
    services = get_services()
    return [
        {
            "id": m.id,
            "alias": m.alias,
            "layer": m.source.layer,
            "feature_count": m.feature_count,
            "bbox": list(m.bbox),
            "operation": m.lineage.operation,
        }
        for m in services.store.list()
    ]
