from geo_agent.agent.tools.datasets.aggregate import aggregate
from geo_agent.agent.tools.datasets.clear_all_datasets import clear_all_datasets
from geo_agent.agent.tools.datasets.delete_dataset import delete_dataset
from geo_agent.agent.tools.datasets.describe_dataset import describe_dataset
from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes
from geo_agent.agent.tools.datasets.rename_dataset import rename_dataset
from geo_agent.agent.tools.datasets.spatial_join import spatial_join
from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay
from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry
from geo_agent.agent.tools.ui.inspect_dataset import inspect_dataset
from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map
from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer
from geo_agent.agent.tools.wfs.list_layers import list_wfs_layers
from geo_agent.agent.tools.wfs.select_features import select_features

# NOTE: `list_datasets` is intentionally NOT registered here. The same metadata is
# re-injected into the system prompt on every model turn (see prompt_builder), so a
# dedicated tool would only be a distractor for the (small, local) model. The function
# still exists in datasets/list_datasets.py and is exercised by its own unit test.
ALL_TOOLS = [
    # WFS server tools
    list_wfs_layers,
    describe_wfs_layer,
    select_features,
    # Local dataset tools
    filter_attributes,
    aggregate,
    describe_dataset,
    spatial_overlay,
    spatial_join,
    transform_geometry,
    # Local dataset management
    delete_dataset,
    rename_dataset,
    clear_all_datasets,
    # UI tools
    show_on_map,
    hide_on_map,
    inspect_dataset,
]

__all__ = [
    "ALL_TOOLS",
    "list_wfs_layers",
    "describe_wfs_layer",
    "select_features",
    "filter_attributes",
    "aggregate",
    "describe_dataset",
    "spatial_join",
    "spatial_overlay",
    "transform_geometry",
    "delete_dataset",
    "rename_dataset",
    "clear_all_datasets",
    "show_on_map",
    "hide_on_map",
    "inspect_dataset",
]
