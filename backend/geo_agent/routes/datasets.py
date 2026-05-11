from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from geo_agent.agent.registry import get_services

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
def list_all() -> list[dict]:
    return [m.model_dump(mode="json") for m in get_services().store.list()]


@router.get("/{dataset_id}/meta")
def get_meta(dataset_id: str) -> dict:
    try:
        return get_services().store.get_meta(dataset_id).model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")


@router.get("/{dataset_id}/geojson")
def get_geojson(dataset_id: str) -> dict:
    try:
        return get_services().store.get_geojson(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")


@router.get("/{dataset_id}/attributes/{attribute}/stats")
def get_attribute_stats(dataset_id: str, attribute: str) -> dict:
    from geo_agent.services.attribute_stats import compute_attribute_stats

    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")
    try:
        return compute_attribute_stats(gj, attribute)
    except KeyError:
        raise HTTPException(404, f"attribute {attribute} not found in dataset {dataset_id}")


class DrawingPayload(BaseModel):
    polygon: dict


class AliasPayload(BaseModel):
    alias: str


@router.post("/drawing")
def create_drawing(payload: DrawingPayload) -> dict:
    services = get_services()
    if payload.polygon.get("type") != "Polygon":
        raise HTTPException(400, "polygon must be a GeoJSON Polygon")

    existing_drawings = sum(
        1 for m in services.store.list() if m.lineage.operation == "user_drawing"
    )
    alias = f"zone_{existing_drawings + 1}"

    rid = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": payload.polygon, "properties": {}}],
        },
        {
            "alias": alias,
            "source": {"type": "user_drawing", "filter_summary": "user-drawn polygon"},
            "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}},
        },
    )
    meta = services.store.get_meta(rid)
    return {
        "id": rid,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
        "layer": None,
        "operation": "user_drawing",
        "parent_ids": meta.lineage.parent_ids,
    }


@router.delete("")
def clear_all() -> dict:
    services = get_services()
    ids = [m.id for m in services.store.list()]
    for i in ids:
        services.store.delete(i)
    return {"deleted": len(ids)}


@router.delete("/{dataset_id}")
def delete_one(dataset_id: str) -> dict:
    services = get_services()
    try:
        services.store.delete(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found") from None
    return {"deleted": dataset_id}


@router.patch("/{dataset_id}")
def rename(dataset_id: str, payload: AliasPayload) -> dict:
    services = get_services()
    new_alias = payload.alias
    if (
        not new_alias
        or any(c.isspace() for c in new_alias)
        or len(new_alias) > 64
    ):
        raise HTTPException(
            400,
            "alias must be non-empty, contain no whitespace, and be at most 64 chars",
        )
    try:
        rid = services.store._resolve_id(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found") from None
    for m in services.store.list():
        if m.id != rid and m.alias == new_alias:
            raise HTTPException(409, f"alias '{new_alias}' already used by {m.id}")
    services.store.update_alias(rid, new_alias)
    return {"id": rid, "alias": new_alias}
