from langchain_core.tools import tool

from geo_agent.agent.registry import get_services


@tool
async def list_wfs_layers() -> list[dict]:
    """List all WFS layers available on the Montreal geomatics server.

    Returns one entry per layer with:
      - name: technical id you pass to select_features (e.g. "montreal:parcs")
      - title: short human-readable label
      - abstract: longer description; use it to pick the right layer

    Call this whenever the user asks about a topic and you don't already know
    which layer holds the data.
    """
    services = get_services()
    layers = await services.wfs.get_layers()
    return [
        {"name": l.name, "title": l.title, "abstract": l.abstract or ""}
        for l in layers
    ]
