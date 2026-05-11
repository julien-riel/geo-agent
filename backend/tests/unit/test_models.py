from datetime import UTC, datetime

import pytest

from geo_agent.models import (
    DatasetMeta,
    LineageInfo,
    SourceInfo,
)


def test_dataset_meta_minimal() -> None:
    m = DatasetMeta(
        id="result_001",
        alias=None,
        source=SourceInfo(type="wfs", layer="montreal:parcs", filter_summary="BBOX(...)"),
        feature_count=42,
        bbox=(-73.7, 45.4, -73.5, 45.6),
        attribute_schema={"name": "string"},
        lineage=LineageInfo(parent_ids=[], operation="select_features", params={}),
        created_at=datetime.now(UTC),
        size_bytes=1234,
    )
    assert m.id == "result_001"
    assert m.feature_count == 42


def test_dataset_meta_serializes_to_json() -> None:
    m = DatasetMeta(
        id="result_001",
        alias="parcs",
        source=SourceInfo(type="wfs", layer="montreal:parcs", filter_summary="..."),
        feature_count=1,
        bbox=(0.0, 0.0, 1.0, 1.0),
        attribute_schema={},
        lineage=LineageInfo(parent_ids=[], operation="select_features", params={}),
        created_at=datetime(2026, 5, 9, tzinfo=UTC),
        size_bytes=10,
    )
    data = m.model_dump(mode="json")
    assert data["id"] == "result_001"
    assert data["created_at"].startswith("2026-05-09")


def test_lineage_with_parents() -> None:
    l = LineageInfo(
        parent_ids=["result_001"],
        operation="filter_attributes",
        params={"predicate": "longueur_m > 100"},
    )
    assert l.parent_ids == ["result_001"]


def test_bbox_validation_rejects_invalid_tuple() -> None:
    with pytest.raises(Exception):
        DatasetMeta(
            id="result_001",
            alias=None,
            source=SourceInfo(type="wfs", layer="x", filter_summary=""),
            feature_count=0,
            bbox=(1.0, 2.0),  # type: ignore[arg-type]
            attribute_schema={},
            lineage=LineageInfo(parent_ids=[], operation="x", params={}),
            created_at=datetime.now(UTC),
            size_bytes=0,
        )


def test_source_info_accepts_user_drawing_type() -> None:
    from geo_agent.models import SourceInfo

    s = SourceInfo(type="user_drawing", filter_summary="user-drawn polygon")
    assert s.type == "user_drawing"


def test_dataset_meta_lite_has_parent_ids_default_empty() -> None:
    from geo_agent.models import DatasetMetaLite

    m = DatasetMetaLite(
        id="result_001",
        alias=None,
        feature_count=1,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer=None,
        operation="user_drawing",
    )
    assert m.parent_ids == []


def test_dataset_meta_lite_accepts_parent_ids() -> None:
    from geo_agent.models import DatasetMetaLite

    m = DatasetMetaLite(
        id="result_005",
        alias="derived",
        feature_count=3,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer=None,
        operation="filter_attributes",
        parent_ids=["result_001"],
    )
    assert m.parent_ids == ["result_001"]
