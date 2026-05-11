from geo_agent.agent.tools.datasets.aggregate import aggregate
from geo_agent.agent.tools.datasets.describe_dataset import describe_dataset
from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes
from geo_agent.agent.tools.datasets.list_datasets import list_datasets
from geo_agent.agent.tools.datasets.spatial_join import spatial_join
from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay
from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry
from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map
from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer
from geo_agent.agent.tools.wfs.list_layers import list_wfs_layers
from geo_agent.agent.tools.wfs.select_features import select_features

# Each new-tool task below appends its import + entry to ALL_TOOLS.
ALL_TOOLS = [
    # WFS server tools
    list_wfs_layers,
    describe_wfs_layer,
    select_features,
    # Local dataset tools
    filter_attributes,
    aggregate,
    describe_dataset,
    list_datasets,
    spatial_overlay,
    spatial_join,
    transform_geometry,
    # UI tools
    show_on_map,
    hide_on_map,
]

__all__ = [
    "ALL_TOOLS",
    "list_wfs_layers",
    "describe_wfs_layer",
    "select_features",
    "filter_attributes",
    "aggregate",
    "describe_dataset",
    "list_datasets",
    "spatial_join",
    "spatial_overlay",
    "transform_geometry",
    "show_on_map",
    "hide_on_map",
]
