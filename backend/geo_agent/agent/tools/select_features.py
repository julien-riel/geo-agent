from typing import Annotated, Any, Literal, Union

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from geo_agent.agent.error_helpers import dataset_created_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.ogc_filter import AttributeFilter, SpatialFilter
from geo_agent.services.wfs_client import TooManyFeaturesError


class PolygonSource(BaseModel):
    """A user-provided GeoJSON Polygon (typically from a map drawing tool)."""

    type: Literal["polygon"]
    polygon: dict = Field(description="GeoJSON Polygon geometry")


class DatasetSource(BaseModel):
    """Chain from an existing dataset's geometry."""

    type: Literal["dataset"]
    dataset_id: str = Field(description="Existing dataset id, e.g. result_001 or a user_drawing id")
    use_geometry: bool = Field(
        default=False,
        description=(
            "False (default): use the dataset's bbox as the filter polygon — fast, coarser. "
            "True: union the dataset's geometries — precise, only works if the union is a single Polygon."
        ),
    )


GeometrySource = Annotated[
    Union[PolygonSource, DatasetSource],
    Field(discriminator="type"),
]


class AttributeFilterInput(BaseModel):
    """Server-side attribute filter for the WFS query. Uses OGC operators."""

    property: str = Field(description="Attribute name from the layer's schema")
    op: Literal["eq", "neq", "lt", "gt", "lte", "gte", "like"] = Field(
        description=(
            "OGC server-side operator. Note: 'in' is NOT supported here — use filter_attributes "
            "for in-memory 'in' filtering. 'like' uses % as wildcard."
        ),
    )
    value: Any = Field(description="Comparison value (string/number)")


def _bbox_polygon(bbox: tuple[float, float, float, float]) -> dict:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def _union_dataset_geometries(geojson: dict) -> dict:
    geoms = [shape(f["geometry"]) for f in geojson.get("features", []) if f.get("geometry")]
    if not geoms:
        raise ValueError("dataset has no geometries")
    merged = unary_union(geoms)
    return mapping(merged)


@tool
async def select_features(
    layer: str,
    geometry_source: GeometrySource,
    spatial_predicate: Literal["intersects", "within", "contains", "bbox", "dwithin"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[str | None, Field(description="Short human-readable name for the new dataset")] = None,
    attribute_filter: AttributeFilterInput | None = None,
    distance_meters: float | None = None,
) -> Command:
    """Select features from a WFS layer with a server-side OGC filter.

    Always returns a fresh dataset; never modifies the input.

    geometry_source examples:
      {"type": "polygon", "polygon": {...GeoJSON Polygon...}}                    # user drawing
      {"type": "dataset", "dataset_id": "result_003", "use_geometry": false}     # bbox of result_003
      {"type": "dataset", "dataset_id": "zone_1_id",   "use_geometry": true}     # geometry of zone_1

    spatial_predicate:
      intersects | within | contains | bbox | dwithin (requires distance_meters)

    attribute_filter (optional, server-side):
      {"property": "type", "op": "eq", "value": "parc"}
      Operators: eq, neq, lt, gt, lte, gte, like (NO 'in' — use filter_attributes for that).

    Returns: {"dataset_id", "alias", "feature_count", "bbox", "attribute_schema"}.
    On failure, an error is stored in state.errors and surfaced as a ToolMessage with code:
      too_many_features, dataset_not_found, unsupported_geometry, bad_input.
    """
    services = get_services()
    gsrc = geometry_source  # already validated by args_schema

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

    schema = await services.wfs.describe_feature_type(layer)
    geom_property = schema.geom_property

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
        af = AttributeFilter(property=attribute_filter.property, op=attribute_filter.op, value=attribute_filter.value)

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
    meta_lite = DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )
    return dataset_created_command(
        meta_lite,
        tool_result={
            "dataset_id": rid,
            "alias": meta.alias,
            "feature_count": meta.feature_count,
            "bbox": list(meta.bbox),
            "attribute_schema": meta.attribute_schema,
        },
        state=state,
        tool_call_id=tool_call_id,
    )
