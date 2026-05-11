def test_all_tools_re_exported_and_named() -> None:
    from geo_agent.agent.tools import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    expected = {
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
        "inspect_dataset",
    }
    assert expected.issubset(names)


def test_graph_uses_all_tools() -> None:
    from geo_agent.agent.graph import TOOLS
    from geo_agent.agent.tools import ALL_TOOLS

    assert TOOLS is ALL_TOOLS
