from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    type: Literal["wfs", "derived", "user_drawing"]
    layer: str | None = None
    filter_summary: str = ""
    request_url: str | None = None
    filter_xml_path: str | None = None


class LineageInfo(BaseModel):
    parent_ids: list[str] = Field(default_factory=list)
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


class DatasetMeta(BaseModel):
    id: str
    alias: str | None = None
    source: SourceInfo
    feature_count: int
    bbox: tuple[float, float, float, float]
    attribute_schema: dict[str, str]
    lineage: LineageInfo
    created_at: datetime
    size_bytes: int


class DatasetMetaLite(BaseModel):
    """Lightweight version for the agent state — no source details."""

    id: str
    alias: str | None
    feature_count: int
    bbox: tuple[float, float, float, float]
    layer: str | None
    operation: str
    parent_ids: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    code: str
    message: str
    suggestion: str | None = None


class WFSLayer(BaseModel):
    name: str
    title: str
    abstract: str | None = None
    default_crs: str
    bbox: tuple[float, float, float, float] | None = None
    attribute_schema: dict[str, str] | None = None  # filled lazily
    geom_property: str | None = None  # filled lazily
