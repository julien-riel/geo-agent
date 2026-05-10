def test_format_datasets_summary_empty() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    assert format_datasets_summary([]) == "Current datasets in this session: (none)"


def test_format_datasets_summary_lists_all_fields() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    summary = format_datasets_summary(
        [
            {
                "id": "result_001",
                "alias": "zone_1",
                "operation": "user_drawing",
                "feature_count": 1,
                "bbox": [-73.6, 45.5, -73.55, 45.55],
            },
            {
                "id": "result_002",
                "alias": "parcs_in_zone",
                "operation": "select_features",
                "feature_count": 47,
                "bbox": [-73.6, 45.5, -73.55, 45.55],
            },
        ]
    )

    assert summary.startswith("Current datasets in this session:\n")
    assert "result_001 (alias=zone_1, operation=user_drawing, 1 features, bbox=[-73.6, 45.5, -73.55, 45.55])" in summary
    assert "result_002 (alias=parcs_in_zone, operation=select_features, 47 features, bbox=[-73.6, 45.5, -73.55, 45.55])" in summary


def test_format_datasets_summary_handles_missing_alias() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    summary = format_datasets_summary(
        [{"id": "result_003", "alias": None, "operation": "select_features", "feature_count": 5, "bbox": [0, 0, 1, 1]}]
    )

    assert "alias=None" in summary
