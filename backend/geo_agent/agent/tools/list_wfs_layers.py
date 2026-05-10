from langchain_core.tools import tool

from geo_agent.agent.registry import get_services


@tool
async def list_wfs_layers() -> list[dict]:
    """List all WFS layers available on the Montreal geomatics server.

    Returns a list of layer summaries with name (technical id), title (human label),
    and abstract (description). Use this first when the user asks about a topic
    you don't recognize, to find which layer contains the relevant data.
    """
    services = get_services()
    layers = await services.wfs.get_layers()
    return [
        {
            "name": l.name,
            "title": l.title,
            "abstract": l.abstract or "",
            "bbox": list(l.bbox) if l.bbox else None,
        }
        for l in layers
    ]
