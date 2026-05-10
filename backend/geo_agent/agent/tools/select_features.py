from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError
from geo_agent.services.ogc_filter import (
    AttributeFilter,
    SpatialFilter,
)
from geo_agent.services.wfs_client import TooManyFeaturesError


class PolygonSource(BaseModel):
    type: Literal["polygon"]
    polygon: dict


class DatasetSource(BaseModel):
    type: Literal["dataset"]
    dataset_id: str
    use_geometry: bool = False  # if False, use bbox; if True, union geometries


class AttributeFilterInput(BaseModel):
    property: str
    op: Literal["eq", "neq", "lt", "gt", "lte", "gte", "like"]
    value: Any


def _bbox_polygon(bbox: tuple[float, float, float, float]) -> dict:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def _union_dataset_geometries(geojson: dict) -> dict:
    """Union all feature geometries in a FeatureCollection into a single GeoJSON geometry."""
    geoms = [shape(f["geometry"]) for f in geojson.get("features", []) if f.get("geometry")]
    if not geoms:
        raise ValueError("dataset has no geometries")
    merged = unary_union(geoms)
    return mapping(merged)


@tool
async def select_features(
    layer: str,
    geometry_source: dict,
    spatial_predicate: Literal["intersects", "within", "contains", "bbox", "dwithin"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    alias: Annotated[str | None, Field(description="Human-readable name for this dataset")] = None,
    attribute_filter: dict | None = None,
    distance_meters: float | None = None,
) -> dict | Command:
    """Select features from a WFS layer using an OGC spatial filter pushed to the server.

    geometry_source must be one of:
      - {"type":"polygon","polygon": <GeoJSON Polygon>}  — typically the user's drawing
      - {"type":"dataset","dataset_id":"result_NNN","use_geometry": false}  — chain from a previous result.
        With use_geometry=false, the bbox of the parent dataset is used (fast).
        With use_geometry=true, geometries are unioned (precise, larger payload).

    Returns: {"dataset_id", "alias", "feature_count", "bbox", "attribute_schema"} on success.
    On failure, the error appears in agent state and is fed back as a tool message.
    """
    services = get_services()

    try:
        gsrc = (PolygonSource if geometry_source.get("type") == "polygon" else DatasetSource).model_validate(geometry_source)
    except Exception as e:
        return tool_error_command(
            ToolError(code="bad_input", message=f"Invalid geometry_source: {e}"),
            tool_call_id,
        )

    if isinstance(gsrc, PolygonSource):
        geom = gsrc.polygon
        parent_ids: list[str] = []
        filter_summary = f"{spatial_predicate}(user_polygon)"
    else:
        try:
            meta = services.store.get_meta(gsrc.dataset_id)
        except FileNotFoundError:
            known = [m.id for m in services.store.list()]
            return tool_error_command(
                ToolError(
                    code="dataset_not_found",
                    message=f"No dataset {gsrc.dataset_id}",
                    suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
                ),
                tool_call_id,
            )
        parent_ids = [gsrc.dataset_id]
        if gsrc.use_geometry:
            gj = services.store.get_geojson(gsrc.dataset_id)
            geom = _union_dataset_geometries(gj)
            if geom["type"] != "Polygon":
                return tool_error_command(
                    ToolError(
                        code="unsupported_geometry",
                        message=(
                            f"Unioned geometry of {gsrc.dataset_id} is {geom['type']}; "
                            "only Polygon is supported as a spatial filter today."
                        ),
                        suggestion=(
                            "Use use_geometry=false (bbox) or chain from a dataset whose "
                            "features form a single polygon."
                        ),
                    ),
                    tool_call_id,
                )
            filter_summary = f"{spatial_predicate}(geometry of {gsrc.dataset_id})"
        else:
            geom = _bbox_polygon(meta.bbox)
            filter_summary = f"{spatial_predicate}(bbox of {gsrc.dataset_id})"

    # Discover geom_property
    schema = await services.wfs.describe_feature_type(layer)
    geom_property = schema.geom_property

    # Build filters
    if spatial_predicate == "dwithin":
        if distance_meters is None:
            return tool_error_command(
                ToolError(code="bad_input", message="dwithin requires distance_meters"),
                tool_call_id,
            )
        sf = SpatialFilter(predicate="dwithin", geometry=geom, geom_property=geom_property, distance_meters=distance_meters)
    else:
        sf = SpatialFilter(predicate=spatial_predicate, geometry=geom, geom_property=geom_property)

    af: AttributeFilter | None = None
    if attribute_filter is not None:
        try:
            ai = AttributeFilterInput.model_validate(attribute_filter)
            af = AttributeFilter(property=ai.property, op=ai.op, value=ai.value)
        except Exception as e:
            return tool_error_command(
                ToolError(code="bad_input", message=f"Invalid attribute_filter: {e}"),
                tool_call_id,
            )

    try:
        gj = await services.wfs.get_features(
            layer=layer,
            spatial_filter=sf,
            attribute_filter=af,
            max_features=services.settings.MAX_FEATURES_PER_QUERY,
        )
    except TooManyFeaturesError as e:
        return tool_error_command(
            ToolError(
                code="too_many_features",
                message=str(e),
                suggestion="Refine the area, add an attribute_filter, or chain from a smaller dataset.",
            ),
            tool_call_id,
        )

    rid = services.store.put(
        gj,
        {
            "alias": alias,
            "source": {"type": "wfs", "layer": layer, "filter_summary": filter_summary},
            "lineage": {
                "parent_ids": parent_ids,
                "operation": "select_features",
                "params": {"layer": layer, "spatial_predicate": spatial_predicate},
            },
        },
    )
    meta = services.store.get_meta(rid)
    return {
        "dataset_id": rid,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
        "attribute_schema": meta.attribute_schema,
    }
