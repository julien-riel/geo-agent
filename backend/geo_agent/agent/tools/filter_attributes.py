from langchain_core.tools import tool

from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError
from geo_agent.services.spatial_ops import AttributePredicate, filter_by_attribute


@tool
async def filter_attributes(
    dataset_id: str,
    predicate: dict,
    alias: str | None = None,
) -> dict:
    """Filter a dataset by an attribute predicate, producing a new dataset.

    predicate is {"property": str, "op": "eq"|"neq"|"lt"|"gt"|"lte"|"gte"|"in", "value": <any>}.
    The new dataset has parent_ids=[<source_dataset_id>] in its lineage.
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return {"error": ToolError(code="dataset_not_found", message=f"No dataset {dataset_id}").model_dump()}

    try:
        pred = AttributePredicate.model_validate(predicate)
    except Exception as e:
        return {"error": ToolError(code="bad_input", message=f"Bad predicate: {e}").model_dump()}

    out = filter_by_attribute(gj, pred)
    new_id = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{pred.property} {pred.op} {pred.value}"},
            "lineage": {
                "parent_ids": [dataset_id],
                "operation": "filter_attributes",
                "params": predicate,
            },
        },
    )
    meta = services.store.get_meta(new_id)
    return {
        "dataset_id": new_id,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
    }
