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


def test_build_prompt_returns_system_message_then_messages() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from geo_agent.agent.prompt_builder import build_prompt

    state = {
        "datasets": [
            {"id": "result_001", "alias": "zone_1", "operation": "user_drawing", "feature_count": 1, "bbox": [0, 0, 1, 1]}
        ],
        "active_layers": [],
        "errors": [],
        "messages": [HumanMessage(content="Trouve les chaussées dans cette zone")],
    }

    out = build_prompt(state)

    assert isinstance(out[0], SystemMessage)
    assert "result_001" in out[0].content
    assert "zone_1" in out[0].content
    assert "You are a geospatial analysis assistant" in out[0].content
    assert len(out) == 2
    assert isinstance(out[1], HumanMessage)
    assert out[1].content == "Trouve les chaussées dans cette zone"


def test_build_prompt_handles_missing_datasets() -> None:
    from langchain_core.messages import SystemMessage

    from geo_agent.agent.prompt_builder import build_prompt

    state = {"messages": [], "active_layers": [], "errors": []}  # no datasets key

    out = build_prompt(state)

    assert isinstance(out[0], SystemMessage)
    assert "(none)" in out[0].content


def test_system_prompt_mentions_hide_on_map() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "hide_on_map" in SYSTEM_PROMPT


def test_system_prompt_has_filter_attributes_example() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    # the example block uses a JSON-like literal so the LLM has a concrete shape to copy
    assert '"op": "in"' in SYSTEM_PROMPT or '"op": "gt"' in SYSTEM_PROMPT


def test_system_prompt_distinguishes_operator_sets() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    # the prompt must call out that 'like' is server-side only and 'in' is in-memory only
    assert "No `in`" in SYSTEM_PROMPT
    assert "No `like`" in SYSTEM_PROMPT


def test_system_prompt_has_error_section() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "too_many_features" in SYSTEM_PROMPT
    assert "dataset_not_found" in SYSTEM_PROMPT


def test_system_prompt_recommends_describe_dataset_before_filter() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "describe_dataset" in SYSTEM_PROMPT
